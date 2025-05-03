from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import mysql.connector
from mysql.connector import Error
import time
import json
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

app = Flask(__name__)
app.secret_key = 'patrohoevenensecretkey'  # Add a secret key for sessions
app.json_encoder = DecimalEncoder  # Use the custom JSON encoder

# Globale variabelen voor de laatst gescande kaart en redirects
last_scanned_uid = None
last_scan_time = 0

# Database connection function to ensure fresh connections
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='Darryll',
            password='Darryllens12',
            database='PatroHoevenen'
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
def summary():
    return render_template("summary.html")

@app.route("/registration")
def registration():
    # Haal het laatste gescande UID op voor automatisch invullen in registratie
    return render_template("registration.html", card_uid=last_scanned_uid)

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
        
        # Controleer of de kaart in de database voorkomt met een verse connectie
        try:
            # Get a fresh connection for each check
            connection = get_db_connection()
            if not connection:
                return jsonify({
                    "status": "error",
                    "message": "Kan geen verbinding maken met de database"
                })
                
            cursor = connection.cursor(dictionary=True)
                
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
                
        except Error as e:
            print(f"Database error: {e}")
            return jsonify({
                "status": "error",
                "message": f"Database fout: {str(e)}"
            })
    else:
        print("No UID received in JSON data")
        return jsonify({"status": "error", "message": "Geen UID ontvangen"})

@app.route("/check_scan")
def check_scan():
    global last_scanned_uid, last_scan_time
    
    # Controleer of er een recente scan is (binnen de laatste 10 seconden)
    if last_scanned_uid and time.time() - last_scan_time < 10:
        print(f"Recent scan found: {last_scanned_uid}")
        
        # Controleer of de kaart in de database voorkomt met een verse connectie
        try:
            # Get a fresh connection for each check
            connection = get_db_connection()
            if not connection:
                return jsonify({
                    "status": "error",
                    "message": "Kan geen verbinding maken met de database"
                })
                
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT * FROM users WHERE card_uid = %s"
            cursor.execute(query, (last_scanned_uid,))
            user = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            # Reset laatste scan tijd om te voorkomen dat dezelfde scan
            # meerdere keren wordt gebruikt
            last_scan_time = 0
            
            if user:
                # Save user info in session
                session['user_name'] = user['name']
                session['card_uid'] = user['card_uid']
                
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
        except Error as e:
            print(f"Database error: {e}")
            return jsonify({
                "status": "error",
                "message": f"Database fout: {str(e)}"
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
            
            # Maak een nieuwe tabel aan voor deze gebruiker met de naam als tabelnaam
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS `{safe_table_name}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                drink_name VARCHAR(255) NOT NULL,
                drink_price DECIMAL(10, 2) NOT NULL,
                added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        insert_query = f"INSERT INTO `{safe_table_name}` (drink_name, drink_price) VALUES (%s, %s)"
        cursor.execute(insert_query, (drink_name, drink_price))
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)