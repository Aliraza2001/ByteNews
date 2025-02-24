from flask import Flask, request, jsonify, make_response, render_template, redirect, flash, url_for, logging, send_file, session
from flask_pymongo import PyMongo
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt
import datetime
from functools import wraps
from bson.json_util import dumps
from flask_login import login_user, login_required, logout_user, current_user
import os
import fitz
from gtts import gTTS
from flask_bcrypt import Bcrypt
import openai
import os
import pandas as pd

app = Flask(__name__)
app.config['MONGO_URI'] = 'mongodb://localhost:27017/local'
app.config['SECRET_KEY'] = ''

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'articles')
app.config['TTS_FOLDER'] = os.path.join(app.static_folder, 'tts_articles')
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'txt'}
openai.api_key = ''

mongo = PyMongo(app)
db = mongo.db
user_db = db.users
article_db = db.articles
edit_db = db.editedArticles

def paraphrase_article(article, model="gpt-3.5-turbo-instruct"):
    # Split the article into sentences
    prompt = f"Reword the following article using more neutral language. Just edit the contents of the text, do not include outside stories. Include the quotes. Try not to shorten it.:\n{article}"
    response = openai.completions.create(
        model=model,
        prompt=prompt,
        temperature=0.7,
        max_tokens=800  # Increase max_tokens to accommodate longer input
    )
    return response.choices[0].text.strip()

def summarize_text(text, model="gpt-3.5-turbo-instruct"):
    prompt = f"Shorten the following text by summarizing it. Don't make it too short and make it roughly half the length, and don't remove the quotes.:\n{text}"
    response = openai.completions.create(
        model=model,
        prompt=prompt,
        temperature=0.7,
        max_tokens=300  # Adjust max_tokens as needed
    )
    return response.choices[0].text.strip()

@app.route('/summarize', methods=['POST'])
def summarize_route():
    # Get the input text from the request
    data = request.get_json()
    text = data['text']

    # Summarize the text
    summary = summarize_text(text)

    # Return the summarized text as a JSON response
    return jsonify({'summary': summary})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/paraphrase', methods=['POST'])
def paraphrase_route():
    # Get the input text from the form
    selected_article_content = request.json.get('selectedArticleContent')
    
    original_text = selected_article_content
    paraphrased_text = paraphrase_article(selected_article_content)

    edit_db.insert_one({'paraphrased': paraphrased_text,
                        'original': original_text})
    
    # Return the paraphrased text as JSON response
    return jsonify({'Article': paraphrased_text})

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ''
    for page_num in range(doc.page_count):
        page = doc[page_num]
        text += page.get_text()
    doc.close()
    return text

def generate_tts(text, output_path):
    tts = gTTS(text=text, lang='en')
    tts.save(output_path)



def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = db.users.find_one({'_id': ObjectId(data['user_id'])})
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)
    return decorator

@app.route('/register', methods=['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        plain_password = request.form.get('password1')
        pass2 = request.form.get('password2')  # Adjust the field name
        
        if len(email) < 6:
            flash('enter a valid Email', category='error')
            pass
        elif len(username) < 1:
            flash('enter Username', category='error')
            pass
        elif plain_password != pass2:
            flash('Passwords do not match', category='error')
            pass
        else:
            print(type(plain_password))
            hashed_password = generate_password_hash(plain_password)

            db.users.insert_one({
                'email': email,
                'username': username,
                'password': hashed_password  # Decode the bytes to a string
            })
            flash('Registration success')

            return redirect(url_for('login_user'))

    elif request.method == 'GET':
        return render_template("sign-up.html", user=current_user)

@app.route('/workshop', methods=['GET'])
def debugPage():
    return render_template('podcast-workshop-episode-management.html')

@app.route('/articlehub', methods=['GET'])
def artHub():
    # Fetch articles from the database
    articles = list(article_db.find({}, {'_id': False}))
    print(articles)  # Debugging statement
    
    # Extract content from text files and add it to the articles
    for article in articles:
        if article['file_path'].endswith('.txt'):
            file_path = os.path.join('static', article['file_path'])  # Prepend 'static/' to file path
            with open(file_path, 'r', encoding='utf-8') as file:
                article['content'] = file.read()
    
    # Render the HTML template with the articles data
    return render_template('article-hub.html', articles=articles)

@app.route('/main', methods=['GET'])
def mainPage():
    # Fetch files from the database
    files = list(article_db.find({}, {'_id': False}))
    
    # Render the HTML template with the files data
    return render_template('index.html', files=files)

@app.route('/landing', methods=['GET'])
def landingPage():
   
    return render_template('landing-page.html')

@app.route('/', methods=['GET'])
def land():
    return render_template('landing-page.html')

@app.route('/login', methods=['GET', 'POST'])
def login_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        print (username)
        user = db.users.find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            token = jwt.encode({
                'user_id': str(user['_id']),
                'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
            }, app.config['SECRET_KEY'])

            return redirect(url_for('mainPage'))
        else:
            flash("Invalid Username or Password")

    return render_template('sign-in.html')

#@app.route('/api/articles/upload', methods=['POST'])
#@token_required
#def upload_article(current_user):
#    articles = db.articles
#    title = request.json['title']
#    content = request.json['content']
#    article_id = articles.insert_one({'userID': current_user['_id'], 'title': title, 'content': content}).inserted_id
#    return jsonify({'articleID': str(article_id)}), 201

#@app.route('/api/articles/<articleID>', methods=['GET'])
#def get_article(articleID):
#    try:
 #       # Convert the articleID to ObjectId for querying MongoDB
 #       obj_id = ObjectId(articleID)
 #   except:
 #       return jsonify({'error': 'Invalid article ID format'}), 400
#
 #   # Query the database for the article
  #  article = mongo.db.articles.find_one({'_id': obj_id})

   # if article:
        # Convert the MongoDB document to JSON
    #    article_json = dumps(article)
     #   return article_json
    #else:
     #   return jsonify({'message': 'Article not found'}), 404

@app.route('/api/articles/<articleID>', methods=['PUT'])
@token_required
def update_article(articleID):
    try:
        # Convert the articleID to ObjectId for querying MongoDB
        obj_id = ObjectId(articleID)
    except:
        return jsonify({'error': 'Invalid article ID format'}), 400

    # Extract the new data for the article from the request body
    article_data = request.json

    # Validate the incoming data (this step is crucial for security and data integrity)
    # Here, you should validate article_data to ensure it contains valid fields
    # For simplicity, this validation step is not shown

    # Update the article in the database
    result = mongo.db.articles.update_one({'_id': obj_id}, {'$set': article_data})

    if result.matched_count == 0:
        return jsonify({'message': 'Article not found'}), 404
    else:
        return jsonify({'message': 'Article updated successfully'}), 200

@app.route('/api/articles/<articleID>', methods=['DELETE'])
@token_required
def delete_article(articleID):
    try:
        # Convert the articleID to ObjectId for querying MongoDB
        obj_id = ObjectId(articleID)
    except:
        return jsonify({'error': 'Invalid article ID format'}), 400

    # Delete the article from the database
    result = mongo.db.articles.delete_one({'_id': obj_id})

    if result.deleted_count == 0:
        return jsonify({'message': 'Article not found'}), 404
    else:
        return jsonify({'message': 'Article deleted successfully'}), 200

@app.route('/api/bias/analyze', methods=['POST'])
@token_required
def analyze_bias(current_user):
    # Simulated code for bias analysis, replace with actual analysis logic
    article_id = request.json['article_id']
    article = db.articles.find_one({'_id': ObjectId(article_id)})
    if not article:
        return jsonify({'message': 'Article not found'}), 404

    # Perform bias analysis, this is just a placeholder
    bias_report = {'bias_level': 'moderate', 'details': 'Details about bias...'}

    # Store bias report in the database
    report_id = db.bias_reports.insert_one(bias_report).inserted_id
    return jsonify({'report_id': str(report_id), 'bias_report': bias_report}), 201

@app.route('/api/bias/reports/<reportID>', methods=['GET'])
@token_required
def get_bias_report(current_user, reportID):
    report = db.bias_reports.find_one({'_id': ObjectId(reportID)})
    if not report:
        return jsonify({'message': 'Bias report not found'}), 404
    return jsonify(report), 200

@app.route('/api/articles/edit', methods=['POST'])
@token_required
def edit_article(current_user):
    article_id = request.json['article_id']
    new_content = request.json['new_content']
    db.articles.update_one({'_id': ObjectId(article_id)}, {'$set': {'content': new_content}})
    return jsonify({'message': 'Article updated'}), 200

@app.route('/api/articles/edits/<editID>', methods=['GET'])
@token_required
def get_article_edit(current_user, editID):
    edit = db.article_edits.find_one({'_id': ObjectId(editID)})
    if not edit:
        return jsonify({'message': 'Article edit not found'}), 404
    return jsonify(edit), 200

@app.route('/api/podcasts/create', methods=['POST'])
@token_required
def create_podcast(current_user):
    # Assume podcast info is in the request, replace with actual podcast creation logic
    podcast_info = request.json
    podcast_id = db.podcasts.insert_one(podcast_info).inserted_id
    return jsonify({'podcast_id': str(podcast_id)}), 201

@app.route('/api/podcasts/<podcastID>', methods=['GET'])
@token_required
def get_podcast(current_user, podcastID):
    podcast = db.podcasts.find_one({'_id': ObjectId(podcastID)})
    if not podcast:
        return jsonify({'message': 'Podcast not found'}), 404
    return jsonify(podcast), 200

@app.route('/api/podcasts/<podcastID>', methods=['DELETE'])
@token_required
def delete_podcast(current_user, podcastID):
    result = db.podcasts.delete_one({'_id': ObjectId(podcastID)})
    if result.deleted_count == 0:
        return jsonify({'message': 'Podcast not found'}), 404
    return jsonify({'message': 'Podcast deleted'}), 200

@app.route('/api/settings', methods=['GET', 'PUT'])
@token_required
def manage_settings(current_user):
    if request.method == 'GET':
        settings = db.system_settings.find_one({'_id': current_user['_id']})
        if not settings:
            return jsonify({'message': 'Settings not found'}), 404
        return jsonify(settings), 200
    elif request.method == 'PUT':
        new_settings = request.json
        db.system_settings.update_one({'_id': current_user['_id']}, {'$set': new_settings}, upsert=True)
        return jsonify({'message': 'Settings updated'}), 200
    
@app.route("/db-check")
def lists():
    print([i for x in mongo.db.data.find({})])
    return jsonify([i for i in mongo.db.data.find({})])

@app.route('/debugMenu')
def index():
    # Replace this path with the actual path to your directory
    directory_path = '/static/articles'
    
    # Get the list of files in the directory
    files = [f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))]

    return render_template('your_template.html', files=files)

##########################################################


@app.route('/debugMode', methods=['GET', 'POST'])
def upload_txt():
    file_content = {}

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Check the file type and read content accordingly
            if filename.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content[filename] = f.read()
            elif filename.endswith('.pdf'):
                file_content[filename] = extract_text_from_pdf(file_path)

            flash('File uploaded successfully')

    file_list = os.listdir(os.path.join(app.static_folder, 'articles'))

    for filename in file_list:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if filename.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content[filename] = f.read()
        elif filename.endswith('.pdf'):
            file_content[filename] = extract_text_from_pdf(file_path)

    tts_folder_path = os.path.join(app.static_folder, 'tts_articles')
    tts_file_list = [f for f in os.listdir(tts_folder_path) if os.path.isfile(os.path.join(tts_folder_path, f))]

    return render_template('debug.html', file_list=file_list, file_content=file_content, tts_file_list=tts_file_list)

@app.route('/generate_tts/<filename>', methods=['POST'])
def generate_tts(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    output_path = os.path.join(app.config['TTS_FOLDER'], f"{filename.rsplit('.', 1)[0]}.mp3")

    if filename.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
            tts = gTTS(text=text, lang='en')
            tts.save(output_path)
    elif filename.endswith('.pdf'):
        text = extract_text_from_pdf(file_path)
        tts = gTTS(text=text, lang='en')
        tts.save(output_path)

    flash(f'TTS generation initiated for {filename}. Please refresh the page after a moment.')
    return redirect('/debugMode')

@app.route('/api/tts_articles', methods=['GET'])
def get_tts_articles():
    tts_folder = app.config['TTS_FOLDER']
    files = [f for f in os.listdir(tts_folder) if os.path.isfile(os.path.join(tts_folder, f))]
    return jsonify({'tts_files': files}), 200


@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    title = request.form['title']
    tags = request.form.get('tags', '').split(',')

    # Ensure lowercase filename and replace spaces with underscores
    filename = file.filename.lower().replace(' ', '_')
    
    # Replace backslashes in the filename with forward slashes
    filename = filename.replace('\\', '/')

    # Ensure lowercase tags
    tags = [tag.strip().lower() for tag in tags]

    # Save the file to the static/articles folder with the provided filename
    file_path = os.path.join('static', 'articles', filename)  # Relative to 'static'

    # Save the file
    file.save(file_path)

    file_data = {
        'title': title,
        'tags': tags,
        'file_path': file_path  # Save the relative file path in the database
    }

    # Insert file data into the database (replace this with your MongoDB insertion logic)
    article_db.insert_one(file_data)

    flash('File uploaded successfully', 'success')

    return redirect(request.referrer)

#########################





if __name__ == '__main__':
    app.run(debug=True)