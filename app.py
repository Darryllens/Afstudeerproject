from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
from mysql.connector import Error
import time
import json
import os
from decimal import Decimal
from functools import wraps  # Toegevoegd voor decorators

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

app = Flask(__name__)
# Verbeterde beveiliging: random secret key genereren of uit env variabele halen
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.json_encoder = DecimalEncoder

# Decorators voor routebeveiliging
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_name' not in session:
            return redirect(url_for('welcome'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'kassa_user' not in session:
            return redirect(url_for('welcome'))
        return f(*args, **kwargs)
    return decorated_function

# Globale variabelen voor de laatst gescande kaart en redirects
last_scanned_uid = None
last_scan_time = 0

# Database connection function with improved security
def get_db_connection():
    try:
        # Verbeterde beveiliging: database credentials uit env variabelen halen
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            user=os.environ.get('DB_USER', 'Darryll'),
            password=os.environ.get('DB_PASSWORD', 'Darryllens12'),
            database=os.environ.get('DB_NAME', 'PatroHoevenen')
        )
        return connection
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None

# Initial database connection
mydb = get_db_connection()
mycursor = mydb.cursor(dictionary=True) if mydb else None

@app.route("/")
def home():
    return render_template("user.html")

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/index")
def index():
    # Redirect to user's personal page if user_name is in session
    if 'user_name' in session and 'card_uid' in session:
        # First verify that the user still exists in the database
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            query = "SELECT * FROM users WHERE card_uid = %s"
            cursor.execute(query, (session['card_uid'],))
            user = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user:
                return redirect(url_for('user_index', user_name=session['user_name']))
            else:
                # User has been removed from database, clear session
                session.clear()
    
    return render_template("index.html")

@app.route("/user/<user_name>")
@login_required  # Deze route heeft nu gebruikersauthenticatie
def user_index(user_name):
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return redirect(url_for('welcome'))
            
        cursor = connection.cursor(dictionary=True)
            
        # Get user information
        query = "SELECT * FROM users WHERE name = %s"
        cursor.execute(query, (user_name,))
        user = cursor.fetchone()
        
        if not user:
            # User no longer exists in database
            session.clear()
            return redirect(url_for('welcome'))
        
        # Controleer of de ingelogde gebruiker toegang heeft tot deze pagina
        if session.get('user_name') != user_name and 'kassa_user' not in session:
            return redirect(url_for('welcome'))
            
        # Get user's drinks from their table
        safe_table_name = ''.join(c for c in user_name if c.isalnum() or c == '_')
        
        try:
            query = f"SELECT * FROM `{safe_table_name}` ORDER BY added_on DESC"
            cursor.execute(query)
            user_drinks = cursor.fetchall()
            
            # Calculate total spent
            total_spent = sum(float(drink['drink_price']) for drink in user_drinks) if user_drinks else 0
            
            cursor.close()
            connection.close()
            
            return render_template("index.html", 
                                  user_name=user_name, 
                                  card_uid=user['card_uid'],
                                  user_drinks=user_drinks,
                                  total_spent=total_spent)
        except Error as e:
            print(f"Error retrieving user drinks: {e}")
            cursor.close()
            connection.close()
            
            # If table doesn't exist, just show empty drinks list
            return render_template("index.html", 
                                  user_name=user_name, 
                                  card_uid=user['card_uid'],
                                  user_drinks=[],
                                  total_spent=0)
    except Error as e:
        print(f"Database error: {e}")
        return redirect(url_for('welcome'))

@app.route("/summary")
@admin_required  # Deze route vereist nu admin-rechten
def summary():
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return redirect(url_for('welcome'))
            
        cursor = connection.cursor(dictionary=True)
            
        # Get all users
        query = "SELECT * FROM users ORDER BY name"
        cursor.execute(query)
        users = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return render_template("summary.html", 
                              users=users,
                              kassa_user=session.get('kassa_user', 'Admin'))
    except Error as e:
        print(f"Database error: {e}")
        return redirect(url_for('welcome'))

@app.route("/registration")
def registration():
    # Haal het laatste gescande UID op voor automatisch invullen in registratie
    return render_template("Registration.html", card_uid=last_scanned_uid)

@app.route("/receive_nfc", methods=["POST"])
def receive_nfc():
    global last_scanned_uid, last_scan_time
    
    # Log alle headers en request data voor debugging
    print("Request headers:", dict(request.headers))
    
    try:
        data = request.get_json()
        print(f"Received data: {data}")  # Log the entire data payload
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Invalid JSON data"})
    
    # Sla de UID op in de globale variabele
    if data and 'uid' in data:
        uid = data['uid']
        last_scanned_uid = uid
        last_scan_time = time.time()  # Sla de huidige tijd op
        print(f"Laatste UID ontvangen: {uid}")
        
        # Get the current route if available
        current_route = data.get('current_route', '')
        print(f"Current route: {current_route}")
        
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return jsonify({
                "status": "error",
                "message": "Kan geen verbinding maken met de database"
            })
            
        cursor = connection.cursor(dictionary=True)
        
        # First check if the card is in the kassa table - redirect to summary regardless of current page
        query = "SELECT * FROM kassa WHERE card_uid = %s"
        cursor.execute(query, (uid,))
        kassa_user = cursor.fetchone()
        
        if kassa_user:
            # Card is in kassa table, redirect to summary
            cursor.close()
            connection.close()
            
            print(f"Kassa user found: {kassa_user['name']}, redirecting to summary")
            session['kassa_user'] = kassa_user['name']
            
            return jsonify({
                "status": "success",
                "message": "Kassa gebruiker gevonden",
                "user": kassa_user,
                "redirect": "/summary"  # Redirect to summary page
            })
        
        # Regular user check (if not a kassa user)
        query = "SELECT * FROM users WHERE card_uid = %s"
        cursor.execute(query, (uid,))
        user = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        if user:
            print("User found:", user)
            # Save user info in session
            session['user_name'] = user['name']
            session['card_uid'] = user['card_uid']
            session['user_id'] = user['id']  # Also save user ID in session
            
            return jsonify({
                "status": "success",
                "message": "Gebruiker gevonden",
                "user": user,
                "redirect": f"/user/{user['name']}"  # Redirect to user's personal page
            })
        else:
            print("User not found for card:", uid)
            # Clear session if it exists
            session.clear()
            
            return jsonify({
                "status": "not_found",
                "message": "Gebruiker niet gevonden voor deze kaart",
                "card_uid": uid,
                "redirect": "/registration"  # Redirect to registration page
            })
    else:
        print("No UID received in JSON data")
        return jsonify({"status": "error", "message": "Geen UID ontvangen"})

@app.route("/check_scan")
def check_scan():
    global last_scanned_uid, last_scan_time
    
    # Get the current route
    current_route = request.args.get('route', '')
    print(f"Check scan called from route: {current_route}")
    
    # Controleer of er een recente scan is (binnen de laatste 10 seconden)
    if last_scanned_uid and time.time() - last_scan_time < 10:
        print(f"Recent scan found: {last_scanned_uid}")
        
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return jsonify({
                "status": "error",
                "message": "Kan geen verbinding maken met de database"
            })
            
        cursor = connection.cursor(dictionary=True)
        
        # Check if the card is in the kassa table - redirect to summary regardless of current page
        query = "SELECT * FROM kassa WHERE card_uid = %s"
        cursor.execute(query, (last_scanned_uid,))
        kassa_user = cursor.fetchone()
        
        if kassa_user:
            # Reset laatste scan tijd
            last_scan_time = 0
            
            # Card is in kassa table, redirect to summary
            cursor.close()
            connection.close()
            
            session['kassa_user'] = kassa_user['name']
            
            return jsonify({
                "status": "success",
                "message": "Kassa gebruiker gevonden",
                "user": kassa_user,
                "redirect": "/summary"  # Redirect to summary page
            })
        
        # Regular user check (if not a kassa user)
        query = "SELECT * FROM users WHERE card_uid = %s"
        cursor.execute(query, (last_scanned_uid,))
        user = cursor.fetchone()
        
        # Reset laatste scan tijd
        last_scan_time = 0
        
        cursor.close()
        connection.close()
        
        if user:
            # Save user info in session
            session['user_name'] = user['name']
            session['card_uid'] = user['card_uid']
            session['user_id'] = user['id']  # Also save user ID in session
            
            return jsonify({
                "status": "success",
                "message": "Gebruiker gevonden",
                "user": user,
                "redirect": f"/user/{user['name']}"  # Redirect to user's personal page
            })
        else:
            # Clear session if it exists
            session.clear()
            
            return jsonify({
                "status": "not_found",
                "message": "Gebruiker niet gevonden voor deze kaart",
                "card_uid": last_scanned_uid,
                "redirect": "/registration"  # Redirect to registration page
            })
    else:
        return jsonify({
            "status": "no_scan",
            "message": "Geen recente scan gevonden"
        })

# Route om nieuwe gebruiker te registreren
@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.form
    
    try:
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return render_template("registration.html", 
                                  error="Kan geen verbinding maken met de database", 
                                  card_uid=data.get('card_uid', ''))
            
        cursor = connection.cursor(dictionary=True)
            
        # Controleer of alle vereiste velden aanwezig zijn
        if 'card_uid' in data and 'name' in data:
            card_uid = data['card_uid']
            name = data['name']
            
            # Gebruik de naam als tabelnaam
            # Maak tabelnaam veilig (alleen alfanumerieke tekens en underscores)
            safe_table_name = ''.join(c for c in name if c.isalnum() or c == '_')
            
            if not safe_table_name:
                cursor.close()
                connection.close()
                return render_template("registration.html", 
                                      error="Naam mag alleen letters, cijfers en underscores bevatten", 
                                      card_uid=card_uid)
            
            # Voeg de nieuwe gebruiker toe aan de database
            query = "INSERT INTO users (card_uid, name) VALUES (%s, %s)"
            cursor.execute(query, (card_uid, name))
            connection.commit()
            
            # Get the newly created user ID
            user_id = cursor.lastrowid
            
            # Maak een nieuwe tabel aan voor deze gebruiker met de naam als tabelnaam
            # UPDATED: Added foreign key reference to users table
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS `{safe_table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                drink_name VARCHAR(255) NOT NULL,
                drink_price DECIMAL(10, 2) NOT NULL,
                added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
            
            print(f"Creating table with query: {create_table_query}")
            cursor.execute(create_table_query)
            connection.commit()
            
            cursor.close()
            connection.close()
            
            print(f"Table '{safe_table_name}' created successfully for user {name}")
            
            # Store user info in session
            session['user_name'] = name
            session['card_uid'] = card_uid
            session['user_id'] = user_id  # Store the user ID in the session
            
            return redirect(url_for('user_index', user_name=name))
        else:
            cursor.close()
            connection.close()
            return render_template("registration.html", 
                                  error="Niet alle vereiste velden zijn ingevuld", 
                                  card_uid=data.get('card_uid', ''))
    except Error as e:
        print(f"Database error: {e}")
        return render_template("registration.html", 
                              error=f"Database fout: {str(e)}", 
                              card_uid=data.get('card_uid', ''))

# Route to add a drink to a user's table
@app.route("/add_user_drink", methods=["POST"])
@admin_required  # Deze route vereist nu admin-rechten
def add_user_drink():
    try:
        data = request.get_json()
        
        if not data or not all(key in data for key in ['user_name', 'drink_name', 'drink_price']):
            return jsonify({
                "success": False,
                "error": "Ontbrekende vereiste gegevens"
            })
        
        user_name = data['user_name']
        drink_name = data['drink_name']
        drink_price = data['drink_price']
        
        # Get a fresh connection
        connection = get_db_connection()
        if not connection:
            return jsonify({
                "success": False,
                "error": "Kan geen verbinding maken met de database"
            })
            
        cursor = connection.cursor(dictionary=True)
            
        # Validate that the user exists
        query = "SELECT * FROM users WHERE name = %s"
        cursor.execute(query, (user_name,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            connection.close()
            return jsonify({
                "success": False,
                "error": f"Geen gebruiker gevonden met naam: {user_name}"
            })
            
        # Create safe table name
        safe_table_name = ''.join(c for c in user_name if c.isalnum() or c == '_')
        
        # Insert the drink into the user's table
        # UPDATED: Added user_id to insert query
        insert_query = f"INSERT INTO `{safe_table_name}` (drink_name, drink_price, user_id) VALUES (%s, %s, %s)"
        cursor.execute(insert_query, (drink_name, drink_price, user['id']))
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": f"{drink_name} toegevoegd aan {user_name}'s rekening"
        })
        
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({
            "success": False,
            "error": f"Database fout: {str(e)}"
        })
    except Exception as e:
        print(f"General error: {e}")
        return jsonify({
            "success": False,
            "error": f"Algemene fout: {str(e)}"
        })

@app.route("/get_user_drinks")
@admin_required  # Deze route vereist nu admin-rechten
def get_user_drinks():
    user_name = request.args.get('user_name')
    if not user_name:
        return jsonify({"success": False, "error": "Geen gebruikersnaam opgegeven"})
    
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Create safe table name
        safe_table_name = ''.join(c for c in user_name if c.isalnum() or c == '_')
        
        try:
            # Get all drinks for the user
            query = f"SELECT * FROM `{safe_table_name}` ORDER BY added_on DESC"
            cursor.execute(query)
            drinks = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            return jsonify({
                "success": True,
                "drinks": drinks
            })
        except Error as e:
            print(f"Error retrieving user drinks: {e}")
            cursor.close()
            connection.close()
            return jsonify({"success": False, "error": f"Fout bij ophalen drankjes: {str(e)}"})
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

@app.route("/delete_drink", methods=["POST"])
@admin_required  # Deze route vereist nu admin-rechten
def delete_drink():
    data = request.get_json()
    
    if not data or not all(key in data for key in ['user_name', 'drink_id']):
        return jsonify({"success": False, "error": "Ontbrekende vereiste gegevens"})
    
    user_name = data['user_name']
    drink_id = data['drink_id']
    
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Create safe table name
        safe_table_name = ''.join(c for c in user_name if c.isalnum() or c == '_')
        
        # Delete the drink
        query = f"DELETE FROM `{safe_table_name}` WHERE id = %s"
        cursor.execute(query, (drink_id,))
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": "Drankje verwijderd"
        })
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

@app.route("/clear_user_drinks", methods=["POST"])
@admin_required  # Deze route vereist nu admin-rechten
def clear_user_drinks():
    data = request.get_json()
    
    if not data or 'user_name' not in data:
        return jsonify({"success": False, "error": "Ontbrekende gebruikersnaam"})
    
    user_name = data['user_name']
    
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # Create safe table name
        safe_table_name = ''.join(c for c in user_name if c.isalnum() or c == '_')
        
        # Delete all drinks for the user
        query = f"DELETE FROM `{safe_table_name}`"
        cursor.execute(query)
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": "Alle drankjes verwijderd"
        })
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

@app.route("/delete_user", methods=["POST"])
@admin_required  # Deze route vereist nu admin-rechten
def delete_user():
    data = request.get_json()
    
    if not data or 'user_name' not in data:
        return jsonify({"success": False, "error": "Ontbrekende gebruikersnaam"})
    
    user_name = data['user_name']
    
    try:
        # Get a fresh database connection
        connection = get_db_connection()
        if not connection:
            return jsonify({"success": False, "error": "Database verbindingsfout"})
            
        cursor = connection.cursor(dictionary=True)
        
        # First, verify that the user exists
        query = "SELECT * FROM users WHERE name = %s"
        cursor.execute(query, (user_name,))
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            connection.close()
            return jsonify({"success": False, "error": "Gebruiker niet gevonden"})
        
        # Create safe table name
        safe_table_name = ''.join(c for c in user_name if c.isalnum() or c == '_')
        
        # We don't need to explicitly drop the user's table anymore
        # because of the ON DELETE CASCADE constraint in the foreign key
        # But we'll keep the code to ensure backward compatibility
        try:
            drop_table_query = f"DROP TABLE IF EXISTS `{safe_table_name}`"
            cursor.execute(drop_table_query)
            connection.commit()
        except Error as e:
            print(f"Error dropping user table: {e}")
            # Continue with deleting the user even if table drop fails
        
        # Delete the user from the users table
        # This will automatically delete all related drinks due to ON DELETE CASCADE
        delete_query = "DELETE FROM users WHERE name = %s"
        cursor.execute(delete_query, (user_name,))
        connection.commit()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            "success": True,
            "message": "Gebruiker verwijderd"
        })
    except Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "error": f"Database fout: {str(e)}"})

# Sessie-bescherming: instellen sessie timeout
@app.before_request
def session_timeout():
    session.permanent = True
    app.permanent_session_lifetime = 3600  # 1 uur sessie timeout

# Route voor logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('welcome'))

# 404 error handler
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    # In productie zet je debug op False
    app.run(host='0.0.0.0', port=5000, debug=False)