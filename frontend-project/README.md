# AutoReview

A web application that automates code review using AI-powered analysis. Upload your projects and receive comprehensive feedback on code quality, potential issues, and improvement suggestions.

## Features

- **User Authentication**: Secure login and registration system
- **Project Upload**: Support for file uploads (ZIP, PDF) and URL submissions
- **AI-Powered Reviews**: Automated code analysis with simulated LLM processing
- **Review History**: Track all your submissions and their status
- **Detailed Reports**: HTML-based review reports with issues and suggestions

## How It Works

| Step 1: Authentication | Step 2: Project Upload |
| :---: | :---: |
| ![Authentication Process](frontend-project/readme_assets/signup.gif) | ![Project Upload](frontend-project/readme_assets/upload.gif) |
| **1. Create account or login**<br>Secure access to your review dashboard | **2. Submit your project**<br>Upload files or provide repository URL |

| Step 3: AI Analysis | Step 4: Review Results |
| :---: | :---: |
| ![Analysis Process](frontend-project/readme_assets/send-to-review.gif) | ![Review Results](frontend-project/readme_assets/view-report.gif) |
| **3. Automated code review**<br>AI system analyzes your code quality | **4. Receive detailed feedback**<br>Get actionable insights and suggestions |


## Technology Stack

- **Backend**: Python Flask with SQLite database
- **Frontend**: HTML, CSS, JavaScript with Tailwind CSS
- **Authentication**: Session-based with password hashing
- **File Processing**: Secure upload handling and storage

## Installation

1. Clone the repository
2. Install dependencies: `pip install flask flask-cors werkzeug`
3. Run the application: `python app.py`
4. Open `http://localhost:5000` in your browser

## API Endpoints

- `POST /api/login` - User authentication
- `POST /api/create-account` - User registration  
- `POST /api/upload-project` - Project submission
- `POST /api/send-for-review` - Initiate code analysis
- `GET /api/user-projects` - Retrieve review history