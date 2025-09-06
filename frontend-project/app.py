from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# In-memory user storage (replace with a real database in production)
users = {
    "t": {"password": "t", "name": "Test User"}
}

htmls_path = './public/'

@app.route('/')
def serve_indexroot():
    return send_from_directory('.', os.path.join(htmls_path,'index.html'))

@app.route('/create-account')
def serve_create_acc():
    return send_from_directory('.', os.path.join(htmls_path,'create-account.html'))

@app.route('/login')
def serve_login():
    return send_from_directory('.', os.path.join(htmls_path,'index.html'))

@app.route('/index')
def serve_index():
    return send_from_directory('.', os.path.join(htmls_path,'index.html'))

@app.route('/main_page')
def serve_main_page():
    return send_from_directory('.', os.path.join(htmls_path,'main_page.html'))

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    print(f"\n\nGOT from logit {username}, {password}\n\n")
    
    if username in users and users[username]['password'] == password:
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'username': username,
                'name': users[username]['name']
            }
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Invalid username or password'
        }), 401

@app.route('/api/create-account', methods=['POST'])
def create_account():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    print(f"\n\nGOT NEW USER  {username}, {password}\n\n")
    
    # Validation
    if not username or not password:
        return jsonify({
            'success': False,
            'message': 'Username and password are required'
        }), 400
        
    if username in users:
        return jsonify({
            'success': False,
            'message': 'Username already exists'
        }), 409
    
    # Store new user
    users[username] = {
        'password': password
    }
    
    return jsonify({
        'success': True,
        'message': 'Account created successfully'
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)