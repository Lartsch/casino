#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flaskext.mysql import MySQL
from flask_mail import Mail, Message
from random import randint
from flask_jsglue import JSGlue
from datetime import datetime

import re, hashlib, json, os, glob, struct, PIL
from PIL import Image 

mysql = MySQL()
mail = Mail()
jsglue = JSGlue()

app = Flask(__name__)
app.config.from_pyfile('db.cfg')
app.config.from_pyfile('mail.cfg')
app.config['PROFILEIMAGE_UPLOAD_FOLDER'] = '/var/www/html/CasinoApp/CasinoApp/static/upload/profileimg'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

APPDOMAIN = 'https://casino.reshade.io'

mysql.init_app(app)
mail.init_app(app)
jsglue.init_app(app)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

def mysql_fetchone(execute, data):
	connection = mysql.connect()
	cursor = connection.cursor()
	cursor.execute(execute, data)
	# Fetch one record and return result
	account = cursor.fetchone()
	cursor.close()
	connection.close()
	return account

def mysql_fetchall(execute, data):
	connection = mysql.connect()
	cursor = connection.cursor()
	cursor.execute(execute, data)
	# Fetch one record and return result
	accounts = cursor.fetchall()
	cursor.close()
	connection.close()
	return accounts

def mysql_fetchall_nodata(execute):
	connection = mysql.connect()
	cursor = connection.cursor()
	cursor.execute(execute)
	# Fetch one record and return result
	accounts = cursor.fetchall()
	cursor.close()
	connection.close()
	return accounts

def mysql_write(execute, data):
	connection = mysql.connect()
	cursor = connection.cursor()
	cursor.execute(execute, data)
	connection.commit()
	cursor.close()
	connection.close()

def sendamail(subjectformail, recipientslist, messagetosend):
	message = Message(subjectformail, recipients = recipientslist)
	message.html = messagetosend
	mail.send(message)

def create_session(userid, username):
	session['loggedin'] = True
	session['id'] = userid
	session['username'] = username

def destroy_session():
	session.pop('loggedin', None)
	session.pop('id', None)
	session.pop('username', None)

def get_md5(data):
	hash_object = hashlib.md5(data.encode())
	return hash_object.hexdigest()

def is_admin():
	adminaccount = mysql_fetchone('SELECT * FROM user WHERE username = %s', (session.get("username"),))
	if adminaccount[8] == 1:
		return True
	else:
		return False

def valid_user():
	if 'loggedin' in session:
		account = mysql_fetchone('SELECT * FROM user WHERE id = %s', (session.get("id"),))
		if account:
			now = datetime.utcnow()
			mysql_write('UPDATE user SET lastactive = %s WHERE id = %s', (now.strftime('%Y-%m-%d %H:%M:%S'), account[0],))
			if account[4] == 0:
				return True
			else:
				destroy_session()
				return False
		else:
			destroy_session()
			return False
	else:
		return False

@app.route('/')
def index():
	# define our default loggedin status to give to the template engine
	isLoggedIn = False
	isAdmin = False
	# if user is logged in, change the loggedin status
	if valid_user():
		isLoggedIn = True
		if is_admin():
			isAdmin = True
	return render_template('home.html', isLoggedIn=isLoggedIn, isAdmin=isAdmin)

@app.route('/login', methods=['GET', 'POST'])
def anmeldung():
	# if user is logged in, redirect to account page
	if valid_user():
		return redirect(url_for('myaccount'))
	# Output message
	msg = ''
	# Check if username and password POST requests exist
	if request.method == 'POST' and 'user' in request.form and 'pass' in request.form:
		# variable shit
		username = request.form['user']
		password = request.form['pass']
		md5_hash = get_md5(password)
		account = mysql_fetchone('SELECT * FROM user WHERE username = %s AND password = %s', (username, md5_hash,))
		# If account exists
		if account:
			# if user is banned, send him off
			if account[4] == 1:
				return render_template('anmeldung.html', msg='User is banned!', isLoggedIn=False, isAdmin=False)
			# if user is not activated, send him off
			if account[7] == 0:
				return render_template('anmeldung.html', msg='User is not activated! Check your mail (also spam folder).', isLoggedIn=False, isAdmin=False)
			# Create session data
			create_session(account[0], account[1])
			now = datetime.utcnow()
			mysql_write('UPDATE user SET lastlogin = %s WHERE username = %s', (now.strftime('%Y-%m-%d %H:%M:%S'), username,))
			# Redirect to account page
			return redirect(url_for('myaccount'))
		else:
			# Account does not exist or username/password incorrect
			msg = 'Incorrect username/password!'
	return render_template('anmeldung.html', msg=msg, isLoggedIn=False, isAdmin=False)

@app.route('/logout')
def logout():
	valid = valid_user()
	# Remove session data
	destroy_session()
	# Redirect
	return redirect(url_for('anmeldung'))

@app.route('/signup', methods=['GET', 'POST'])
def registrierung():
	# if user is logged in, redirect to account page
	if valid_user():
		return redirect(url_for('myaccount'))
	# Output message
	msg = ''
	# Check if username, password and email POST requests exist
	if request.method == 'POST' and 'user' in request.form and 'email' in request.form and 'pass' in request.form:
		# Create variables for easy access
		username = request.form['user']
		password = request.form['pass']
		email = request.form['email']
		account = mysql_fetchone('SELECT * FROM user WHERE username = %s OR email = %s', (username, email,))
		# If account exists perform checks
		if account:
			msg = 'Account already exists! (username or email)'
		elif not username or not password or not email:
			msg = 'Please fill out the form!'
		elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
			msg = 'Invalid email address!'
		elif not re.match(r'[A-Za-z0-9]+', username):
			msg = 'Username must contain only characters and numbers!'
		else:
			otp = randint(000000,999999)
			# Account doesnt exist and the form data is valid, insert new account into table
			md5_hash = get_md5(password)
			mysql_write('INSERT INTO user VALUES (NULL, %s, %s, %s, 0, 20, %s, 0, 0, NULL, NULL, 0, NULL)', (username, email, md5_hash, otp))
			otpstring = str(otp)
			sendamail("Account activation", [email], "<h3>Activation link:</h3><p><a href='" + APPDOMAIN + "/activate?otp=" + otpstring + "&user=" + username +"'>"+ APPDOMAIN +"/activate?otp=" + otpstring + "&user=" + username +"</a></p>")
			msg = 'Check your mail to confirm registration! Also look in spam.'
	elif request.method == 'POST':
		# Form is empty
		msg = 'Please fill out the form!'
	# Show registration form with message
	return render_template('registrierung.html', msg=msg, isLoggedIn=False, isAdmin=False)

@app.route('/my-account', methods=['GET', 'POST'])
def myaccount():
	if valid_user():
		if is_admin():
			return redirect(url_for('adminpanel'))
	else:
		return redirect(url_for('anmeldung'))
	username = ''
	email = ''
	msgchangepw = ''
	msgdeleteacc = ''
	msgimage = ''
	extension = ''
	hasimage = False
	accountdata = mysql_fetchone('SELECT * FROM user WHERE id = %s AND username = %s', (session.get("id"), session.get("username"),))
	if accountdata[11] == 1:
		hasimage = True
		profileimage = glob.glob(app.config['PROFILEIMAGE_UPLOAD_FOLDER'] + '/' + str(session.get("id")) + '.*')
		extension = os.path.splitext(profileimage[0])[1]
	if request.method == 'POST' and 'currentpassword' in request.form and 'newpassword' in request.form:
		# Create variables for easy access
		currentpassword = request.form['currentpassword']
		newpassword = request.form['newpassword']
		md5_hash_current = get_md5(currentpassword)
		md5_hash_new = get_md5(newpassword)
		account = mysql_fetchone('SELECT * FROM user WHERE username = %s AND password = %s', (session.get("username"), md5_hash_current,))
		if account:
			mysql_write('UPDATE user SET password = %s WHERE username = %s', (md5_hash_new, session.get("username"),))
			msgchangepw = 'Password updated successfully! :)'
		else:
			msgchangepw = 'Wrong current password!'
	if request.method == 'POST' and 'confirmpassword' in request.form:
		# Create variables for easy access
		currentpassword = request.form['confirmpassword']
		md5_hash_current = get_md5(currentpassword)
		account = mysql_fetchone('SELECT * FROM user WHERE username = %s AND password = %s', (session.get("username"), md5_hash_current,))
		if account:
			mysql_write('DELETE FROM user WHERE username = %s', (session.get("username"),))
			destroy_session()
			return redirect(url_for('index'))
		else:
			msgdeleteacc = 'Wrong current password!'
	if request.method == 'POST' and 'image' in request.files:
		file = request.files['image']
		if file.filename == '':
			msgimage = 'Please select a valid file.'
		else:
			if file and allowed_file(file.filename):
				fileList = glob.glob(app.config['PROFILEIMAGE_UPLOAD_FOLDER'] + '/' + str(session.get("id")) + '.*')
				for filePath in fileList:
					try:
						os.remove(filePath)
					except:
						msgimage = 'An error occured.'
				ext = os.path.splitext(file.filename)[1]
				file.save(os.path.join(app.config['PROFILEIMAGE_UPLOAD_FOLDER'], str(session.get("id")) + ext))
				mysql_write('UPDATE user SET profileimg = 1, profileimgext = %s WHERE id = %s', (ext, session.get("id"),))
				pilimg = PIL.Image.open(os.path.join(app.config['PROFILEIMAGE_UPLOAD_FOLDER'], str(session.get("id")) + ext))
				pilheight, pilwidth = pilimg.size
				if str(pilheight) == str(pilwidth):
					if pilwidth <= 600:
						hasimage = True
						extension = ext
						msgimage = 'Image was uploaded!'
					else:
						hasimage = False
						for filePath in fileList:
							try:
								os.remove(filePath)
							except:
								msgimage = 'An error occured.'
						mysql_write('UPDATE user SET profileimg = 0, profileimgext = NULL WHERE id = %s', (session.get("id"),))
						msgimage = 'Image is too large (max. 600x600)!'
				else:
					hasimage = False
					for filePath in fileList:
							try:
								os.remove(filePath)
							except:
								msgimage = 'An error occured.'
					mysql_write('UPDATE user SET profileimg = 0, profileimgext = NULL WHERE id = %s', (session.get("id"),))
					msgimage = 'Image is not a square!'
			else:
				msgimage = 'File not accepted.'
	deleteimage = request.args.get("deleteimage")
	if deleteimage == "True":
		if request.environ.get('HTTP_REFERER') is not None:
			if request.environ.get('HTTP_REFERER') == APPDOMAIN + url_for('myaccount'):
				msgimage = deleteimage
				if accountdata[11] == 1:
					hasimage = False
					fileList = glob.glob(app.config['PROFILEIMAGE_UPLOAD_FOLDER'] + '/' + str(session.get("id")) + '.*')
					for filePath in fileList:
						try:
							os.remove(filePath)
						except:
							msgimage = 'An error occured.'
					mysql_write('UPDATE user SET profileimg = 0 WHERE id = %s', (session.get("id"),))
					msgimage = 'Image was deleted!'
				else:
					msgimage = 'You do not have an image.'
	return render_template('myaccount.html', isLoggedIn=True, isAdmin=False, username=accountdata[1], email=accountdata[2], balance=accountdata[5], msgchangepw=msgchangepw, msgdeleteacc=msgdeleteacc, msgimage=msgimage, userid=session.get("id"), hasimage=hasimage, extension=extension)

@app.route('/games/slotmachine')
def slotmachine():
	if valid_user():
		if is_admin():
			return redirect(url_for('adminpanel'))
	else:
		return redirect(url_for('anmeldung'))
	return render_template('slotmachine.html', isLoggedIn=True, isAdmin=False)

@app.route('/activate', methods=['GET'])
def activate():
	# if user is logged in, redirect to account page
	if valid_user():
		return redirect(url_for('myaccount'))
	success = False
	if request.args.get('otp') is None or request.args.get('user') is None:
		return render_template('activation.html', success=success, isLoggedIn=False, isAdmin=False)
	else:
		otp = int(request.args.get('otp')) #if key doesn't exist, returns None
		user = str(request.args.get('user')) #if key doesn't exist, returns None
		account = mysql_fetchone('SELECT * FROM user WHERE username = %s AND activationcode = %s', (user, otp,))
		if account:
			mysql_write('UPDATE user SET activated = 1 WHERE username = %s', (account[1],))
			success = True
	return render_template('activation.html', success=success, isLoggedIn=False, isAdmin=False)

@app.route('/resetpassword', methods=['GET', 'POST'])
def resetpassword():
	# if user is logged in, redirect to account page
	if valid_user():
		return redirect(url_for('myaccount'))
	msg = ''
	if request.method == 'POST' and 'email' in request.form and 'user' in request.form:
		# Create variables for easy access
		email = request.form['email']
		user = request.form['user']
		account = mysql_fetchone('SELECT * FROM user WHERE email = %s AND username = %s', (email,user,))
		if account:
			password = str(randint(000000000000,999999999999))
			md5_hash = get_md5(password)
			mysql_write('UPDATE user SET password = %s WHERE username = %s', (md5_hash,account[1],))
			sendamail('Password reset', [account[2]], "<h4>New login data is:</h4><p>Username: " + account[1] + "</p><p>Password: " + password + "</p>")
			msg = 'Your new password has been sent to your email. Also check your spam folder.'
		else:
			msg = 'User not found.'
	return render_template('resetpassword.html', msg=msg, isLoggedIn=False, isAdmin=False)

@app.route('/sendcredits', methods=['GET', 'POST'])
def sendcredits():
	if valid_user():
		if is_admin():
			return redirect(url_for('adminpanel'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	if request.method == 'POST' and 'user' in request.form and 'amount' in request.form:
		user = request.form['user']
		amountform = request.form['amount']
		if amountform.isdecimal():
			amount = int(amountform)
			account = mysql_fetchone('SELECT * FROM user WHERE username = %s', (user,))
			if account:
				sendfromaccount = mysql_fetchone('SELECT * FROM user WHERE username = %s', (session.get("username",)))
				if(sendfromaccount[1] == account[1]):
					msg = 'You cannot send credits to yourself.'
				else:
					if (sendfromaccount[5] >= amount):
						mysql_write('UPDATE user SET balance = %s WHERE username = %s', (int(sendfromaccount[5])-amount, sendfromaccount[1],))
						mysql_write('UPDATE user SET balance = %s WHERE username = %s', (int(account[5])+amount, account[1],))
						msg = 'Credits sent successfully to user "' + account[1] + '"'
					else:
						msg = 'You do not have enough credits.'
			else:
				msg = 'User not found.'
		else:
			msg = 'Amount needs to be a number!'
	return render_template('sendcredits.html', isLoggedIn=True, isAdmin=False, msg=msg, credits=mysql_fetchone('SELECT * FROM user WHERE username = %s', (session.get("username",)))[5])

#@app.route('/_getcredits')
#def getcredits():
#	return jsonify(amount=10)

@app.route('/my-account/buycredits', methods=['GET', 'POST'])
def buycredits():
	if valid_user():
		if is_admin():
			return redirect(url_for('adminpanel'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	if request.method == 'POST' and 'package' in request.form and 'name' in request.form and 'ccnumber' in request.form and 'ccv' in request.form:
		if request.form['package'] is '' or request.form['name'] is '' or request.form['ccnumber'] is '' or request.form['ccv'] is '':
			msg = 'Fill out the form!'
		else:
			package = int(request.form['package'])
			account = mysql_fetchone('SELECT * FROM user WHERE username = %s', (session.get("username"),))
			if account:
				mysql_write('UPDATE user SET balance = %s WHERE username = %s', (int(account[5])+package, account[1],))
				msg = 'Your purchase for account "' + account[1] + '" was successful!'
			else:
				msg = 'Unknown error occured.'
	return render_template('buycredits.html', isLoggedIn=True, isAdmin=False, msg=msg, credits=mysql_fetchone('SELECT * FROM user WHERE username = %s', (session.get("username",)))[5])

@app.route('/adminpanel', methods=['GET', 'POST'])
def adminpanel():
	if valid_user():
		if not is_admin():
			return redirect(url_for('myaccount'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	accountdata = mysql_fetchone('SELECT * FROM user WHERE username = %s', (session.get("username"),))
	return render_template('adminpanel.html', isLoggedIn=True, isAdmin=True, msg=msg, username=accountdata[1], email=accountdata[2])

@app.route('/adminpanel/edituser', methods=['GET', 'POST'])
def edituser():
	if valid_user():
		if not is_admin():
			return redirect(url_for('myaccount'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	username = ''
	email = ''
	balance = ''
	activated = ''
	banned = ''
	isadmin = ''
	userid = ''
	editmode = False
	if request.args.get("user") is None:
		if request.method == 'POST' and 'user' in request.form:
			if request.form['user'] == '':
				msg = 'Fill out the form!'
			else:
				usernameform = request.form['user']
				account = mysql_fetchone('SELECT * FROM user WHERE username = %s', (usernameform,))
				if account:
					editmode = True
					username = account[1]
					email = account[2]
					balance = account[5]
					activated = account[7]
					banned = account[4]
					isadmin = account[8]
					userid = account[0]
				else:
					msg = 'Account not found!'
		if request.method == 'POST' and 'userchange' in request.form and 'emailchange' in request.form and 'balancechange' in request.form and 'activatedchange' in request.form and 'bannedchange' in request.form and 'isadminchange' in request.form:
			if request.form['userchange'] == '' or request.form['emailchange'] == '' or request.form['balancechange'] == '' or request.form['activatedchange'] == '' or request.form['bannedchange'] == '' or request.form['isadminchange'] == '':
				account = mysql_fetchone('SELECT * FROM user WHERE id = %s', (request.form['userid'],))
				editmode = True
				username = account[1]
				email = account[2]
				balance = account[5]
				activated = account[7]
				banned = account[4]
				isadmin = account[8]
				userid = account[0]
				msg = 'One or more fields were empty! Please try again.'
			else:
				username = request.form['userchange']
				email = request.form['emailchange']
				balance = request.form['balancechange']
				activated = request.form['activatedchange']
				banned = request.form['bannedchange']
				isadmin = request.form['isadminchange']
				userid = request.form['userid']
				mysql_write('UPDATE user SET username = %s, email = %s, balance = %s, activated = %s, banned = %s, isadmin = %s WHERE id = %s', (username, email, balance, activated, banned, isadmin, userid,))
				if request.form['passwordchange'] != '':
					md5_hash = get_md5(request.form['passwordchange'])
					mysql_write('UPDATE user SET password = %s WHERE id = %s', (md5_hash, userid,))
				editmode = False
				msg = 'User "' + mysql_fetchone('SELECT * FROM user WHERE id = %s', (userid,))[1] + '" with ID ' + userid + ' was edited!'
	else:
		if request.environ.get('HTTP_REFERER') is not None:
			if request.environ.get('HTTP_REFERER') == APPDOMAIN + url_for('showusers'):
				usernameform = request.args.get("user")
				account = mysql_fetchone('SELECT * FROM user WHERE username = %s', (usernameform,))
				if account:
					editmode = True
					username = account[1]
					email = account[2]
					balance = account[5]
					activated = account[7]
					banned = account[4]
					isadmin = account[8]
					userid = account[0]
	return render_template('edituser.html', isLoggedIn=True, isAdmin=True, msg=msg, editmode=editmode, username=username, email=email, balance=balance, activated=activated, banned=banned, isadmin=isadmin, userid=userid)

@app.route('/adminpanel/showusers', methods=['GET', 'POST'])
def showusers():
	if valid_user():
		if not is_admin():
			return redirect(url_for('myaccount'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	users = mysql_fetchall_nodata('SELECT * FROM user')
	return render_template('showusers.html', isLoggedIn=True, isAdmin=True, msg=msg, users=users)

@app.route('/adminpanel/deleteuser', methods=['GET', 'POST'])
def deleteuser():
	if valid_user():
		if not is_admin():
			return redirect(url_for('myaccount'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	if request.args.get("user") is None:
		if request.method == 'POST' and 'user' in request.form:
			if request.form['user'] == '':
				msg = 'Enter a username!'
			else:
				username = request.form['user']
				account = mysql_fetchone('SELECT * FROM user WHERE username = %s', (username,))
				if account:
					mysql_write('DELETE FROM user WHERE username = %s', (username,))
					msg = 'User deleted!'
				else:
					msg = 'User not found!'
	else:
		if request.environ.get('HTTP_REFERER') is not None:
			if request.environ.get('HTTP_REFERER') == APPDOMAIN + url_for('showusers') or request.environ.get('HTTP_REFERER') == APPDOMAIN + url_for('deleteuser'):
				return render_template('deleteuser.html', isLoggedIn=True, isAdmin=True, username=request.args.get("user"))
	return render_template('deleteuser.html', isLoggedIn=True, isAdmin=True, msg=msg)

@app.route('/adminpanel/adduser', methods=['GET', 'POST'])
def adduser():
	if valid_user():
		if not is_admin():
			return redirect(url_for('myaccount'))
	else:
		return redirect(url_for('anmeldung'))
	msg = ''
	# Check if username, password and email POST requests exist
	if request.method == 'POST' and 'user' in request.form and 'email' in request.form and 'pass' in request.form and 'balance' in request.form and 'isadmin' in request.form:
		# Create variables for easy access
		username = request.form['user']
		password = request.form['pass']
		email = request.form['email']
		balance = request.form['balance']
		isadmin = request.form['isadmin']
		account = mysql_fetchone('SELECT * FROM user WHERE username = %s OR email = %s', (username, email,))
		# If account exists perform checks
		if account:
			msg = 'Account already exists! (username or email)'
		elif not username or not password or not email or not balance or not isadmin:
			msg = 'Please fill out the form!'
		elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
			msg = 'Invalid email address!'
		elif not re.match(r'[A-Za-z0-9]+', username):
			msg = 'Username must contain only characters and numbers!'
		else:
			otp = randint(000000,999999)
			# Account doesnt exist and the form data is valid, insert new account into table
			md5_hash = get_md5(password)
			mysql_write('INSERT INTO user VALUES (NULL, %s, %s, %s, 0, %s, %s, 1, %s, NULL, NULL, 0, NULL)', (username, email, md5_hash, balance, otp, isadmin,))
			msg = 'User was added!'
	return render_template('adduser.html', isLoggedIn=True, isAdmin=True, msg=msg)