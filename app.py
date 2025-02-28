from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
import mysql.connector
from datetime import datetime
import logging

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management
CORS(app, supports_credentials=True)  # Enable CORS with credentials

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database connection
mydb = mysql.connector.connect(
    host='localhost',
    user='Darryll',
    password='Darryllens12',
    database='PatroHoevenen'
)
mycursor = mydb.cursor(dictionary=True)

# Global variable to track last scanned card
last_scanned_uid = None

# Routes for HTML pages
@app.route('/')
def login():
    return render_template('user.html')

@app.route('/welcome.html')
def welcome():
    # Clear any previous session data when accessing welcome page
    session.pop('pending_uid', None)
    return render_template('welcome.html')

@app.route('/index.html/<card_uid>')
def index(card_uid):
    return render_template('index.html', card_uid=card_uid)

@app.route('/summary.html')
def summary():
    return render_template('summary.html')

@app.route('/registration.html')
def registration():
    # Get UID from session if available
    uid = session.get('pending_uid', '')
    logger.debug(f"Registration page accessed with UID from session: {uid}")
    if not uid:
        # If no pending_uid in session, check if there's a global last scanned
        global last_scanned_uid
        uid = last_scanned_uid or ''
        logger.debug(f"No UID in session, using last scanned: {uid}")
    return render_template('registration.html', uid=uid)

# Dedicated route for NFC UIDs
@app.route('/nfc_uid', methods=['POST'])
def handle_nfc_uid():
    try:
        data = request.json
        if not data or 'uid' not in data:
            return jsonify({'success': False, 'error': 'No UID provided.'})

        uid = data['uid']
        logger.debug(f"Received NFC UID: {uid}")
        
        # Check if this UID is registered to a user
        mycursor.execute("SELECT * FROM users WHERE card_uid = %s", (uid,))
        user = mycursor.fetchone()
        mydb.commit()
        
        if user:
            # User found - return user info and success
            logger.debug(f"User found for UID {uid}: {user['name']}")
            return jsonify({
                'success': True,
                'message': f"Welcome, {user['name']}!",
                'user_id': user['id'],
                'user_name': user['name'],
                'redirect': f'/index.html/{uid}'  # Redirect to index page
            })
        else:
            # Unknown UID - store in session and global variable
            logger.debug(f"Unknown UID {uid}, setting pending_uid in session")
            session['pending_uid'] = uid
            # Also store in global variable as backup
            global last_scanned_uid
            last_scanned_uid = uid
            # Make sure the session is saved
            session.modified = True
            
            return jsonify({
                'success': False,
                'message': "Unknown card, please register",
                'status': 'unknown',
                'redirect': '/registration.html'  # Redirect to registration page
            })
            
    except Exception as e:
        logger.error(f"Error in handle_nfc_uid: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# API endpoint for user registration
@app.route('/register_user', methods=['POST'])
def register_user():
    try:
        data = request.form
        if not data or 'name' not in data or 'card_uid' not in data:
            return jsonify({'success': False, 'error': 'Missing required fields.'})
        
        name = data['name']
        uid = data['card_uid']
        logger.debug(f"Registering user: {name} with UID: {uid}")
        
        # Register the user
        sql = "INSERT INTO users (card_uid, name, registration_date) VALUES (%s, %s, %s)"
        values = (uid, name, datetime.utcnow())
        mycursor.execute(sql, values)
        mydb.commit()
        
        # Create a new table for the user
        table_name = name.replace(" ", "_")  # Replace spaces with underscores for table name
        create_table_sql = f"""
        CREATE TABLE {table_name} (
            id INT AUTO_INCREMENT PRIMARY KEY,
            drink_name VARCHAR(255),
            drink_price DECIMAL(10, 2),
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        mycursor.execute(create_table_sql)
        mydb.commit()
        
        # Clear the pending UID from session and global variable
        session.pop('pending_uid', None)
        global last_scanned_uid
        last_scanned_uid = None
        
        return jsonify({
            'success': True,
            'message': f"User {name} registered successfully!",
            'redirect': '/welcome.html'
        })
    except Exception as e:
        logger.error(f"Error in register_user: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# API endpoints for drinks
@app.route('/add_drink.php', methods=['GET', 'POST', 'DELETE'])
def handle_drinks():
    if request.method == 'GET':
        try:
            mycursor.execute("SELECT * FROM drankjes")
            results = mycursor.fetchall()
            return jsonify({
                'success': True,
                'data': [{
                    'id': row['id'],
                    'naam': row['naam'],
                    'prijs': row['prijs'],
                    'toegevoegd_op': row['toegevoegd_op'].strftime('%Y-%m-%d %H:%M:%S')
                } for row in results]
            })
        except Exception as e:
            logger.error(f"Error getting drinks: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    elif request.method == 'POST':
        try:
            data = request.json
            if not data or 'drink' not in data or 'price' not in data:
                return jsonify({'success': False, 'error': 'No drink or price specified.'})

            sql = "INSERT INTO drankjes (naam, prijs, toegevoegd_op) VALUES (%s, %s, %s)"
            values = (data['drink'], float(data['price']), datetime.utcnow())
            mycursor.execute(sql, values)
            mydb.commit()

            return jsonify({
                'success': True,
                'message': f"{data['drink']} has been added to the database for €{data['price']}!"
            })
        except Exception as e:
            logger.error(f"Error adding drink: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

    elif request.method == 'DELETE':
        try:
            sql = "DELETE FROM drankjes"
            mycursor.execute(sql)
            mydb.commit()
            return jsonify({'success': True, 'message': 'All drinks have been deleted.'})
        except Exception as e:
            logger.error(f"Error deleting drinks: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})

# API endpoint to check if a card has been scanned
@app.route('/check_scan', methods=['GET'])
def check_scan():
    # Check session for pending_uid
    uid = session.get('pending_uid', None)
    logger.debug(f"Check scan called, pending_uid in session: {uid}")
    
    # If nothing in session, check global variable
    if not uid:
        global last_scanned_uid
        uid = last_scanned_uid
        logger.debug(f"No pending_uid in session, using last_scanned_uid: {uid}")
        
        # If we have a last scanned UID but not in session, add it to session
        if uid:
            session['pending_uid'] = uid
            session.modified = True
            logger.debug(f"Added last_scanned_uid to session: {uid}")
    
    if uid:
        # Check if this UID is registered to a user
        mycursor.execute("SELECT * FROM users WHERE card_uid = %s", (uid,))
        user = mycursor.fetchone()
        
        if user:
            logger.debug("Redirecting to index")
            return jsonify({
                'success': True,
                'redirect': f'/index.html/{uid}'
            })
        else:
            logger.debug("Redirecting to registration")
            return jsonify({
                'success': False, 
                'redirect': 'registration',
                'uid': uid
            })
    else:
        logger.debug("No card scanned yet")
        return jsonify({'success': False})

# Add a route to manually trigger redirection for testing
@app.route('/force_registration/<uid>')
def force_registration(uid):
    session['pending_uid'] = uid
    global last_scanned_uid
    last_scanned_uid = uid
    return redirect('/registration.html')

if __name__ == '__main__':
    # Create users table if it doesn't exist (without table_name column)
    try:
        # First check if the table exists
        mycursor.execute("SHOW TABLES LIKE 'users'")
        table_exists = mycursor.fetchone()
        
        if table_exists:
            # Table exists, check if we need to alter it to remove table_name column
            mycursor.execute("SHOW COLUMNS FROM users LIKE 'table_name'")
            column_exists = mycursor.fetchone()
            
            if column_exists:
                # Column exists, remove it
                logger.info("Removing table_name column from users table")
                mycursor.execute("ALTER TABLE users DROP COLUMN table_name")
                mydb.commit()
                logger.info("table_name column removed successfully")
        else:
            # Table doesn't exist, create it without table_name column
            logger.info("Creating users table without table_name column")
            mycursor.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                card_uid VARCHAR(100) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
            mydb.commit()
            logger.info("users table created successfully")
            
    except Exception as e:
        logger.error(f"Error managing users table: {e}")
        
    app.run(debug=True, host='0.0.0.0', port=5000)