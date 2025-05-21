# Flask NFC Drink Management System

This project is a Flask application designed to manage drinks and user registrations using NFC card scanning. Each user has a unique card, and the application dynamically generates content based on the card UID.

## Project Structure

```
flask-app
├── templates
│   ├── index.html          # Template for the index page, dynamically displays content based on card UID.
│   ├── user.html           # Template for the user login page.
│   ├── Registration.html    # Template for the user registration page.
│   ├── welcome.html        # Template for the welcome page after login or registration.
│   └── summary.html        # Template for displaying a summary of actions or data.
├── app.py                  # Main application logic, handles routing and database connections.
├── requirements.txt        # Lists dependencies required for the project.
└── README.md               # Documentation for the project, including setup instructions and usage guidelines.
```

## Setup Instructions

You can find the instructions in the file "Dossier" in the folder "Documentatie".

## Usage

- **User Registration**: Users can register by providing their name and NFC card UID. This will create a unique table for each user to store their drink data.
- **NFC Scanning**: Users can scan their NFC cards to access their unique index page, which displays their drink information.
- **Drink Management**: Admins can add drinks to the database, which will be stored in a separate table for each user.

## Contributing

Feel free to submit issues or pull requests for improvements or bug fixes. 

## License

This project is licensed under the MIT License.
