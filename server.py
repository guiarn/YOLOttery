from flask import Flask, request, render_template, url_for
from random import randint
import requests
import database
import base64
import schedule
import time
import config

app = Flask(__name__)

TTL = 50
jackpot = 10.0
inityo = 0
inityoleft = 10

def decodeURL (base):
	h = base64.urlsafe_b64decode(base).decode('ascii')
	yleft,r,prize,name,top = h.split('+')
	top = top.split(';')
	return (yleft,r,prize,name,top)

def encodeURL (yleft,r,jp,top,name):
	s = str(yleft) + '+'
	s += str(r) + '+'
	s += str(jp) + '+'
	s += str(name) + '+'
	s += ';'.join(top)
	return base64.urlsafe_b64encode(s.encode('ascii'))

def existsUser(user):
	result = database.query_db('SELECT * FROM users WHERE name = "%s"' % user)
	return len(result) != 0

def existsLocation(latitud, longitud):
	result = database.query_db('SELECT * FROM locations WHERE latitud = %f AND longitud = %f' % (latitud, longitud))
	return len(result) != 0

def insertLocation(latitud, longitud):
	database.query_db('INSERT INTO locations VALUES (%f, %f, %d, %f)' % (latitud, longitud, TTL, jackpot))

def existsYoBoard(user, latitud, longitud):
	result = database.query_db('SELECT * FROM yoboard WHERE name = "%s" AND latitud = %f AND longitud = %f' % (user, latitud, longitud))
	return len(result) != 0

def insertYoBoard(user, latitud, longitud):
	database.query_db('INSERT INTO yoboard VALUES ("%s", %f, %f, %d)' % (user, latitud, longitud, inityo))

def updateTTLs(user, latitud, longitud):
	result = database.query_db('UPDATE users SET TTL = %d, latitud = %f, longitud = %f WHERE name = "%s"' % (TTL, latitud, longitud, user))
	database.query_db('UPDATE locations SET TTL = %d WHERE latitud = %f AND longitud = %f' % (TTL, latitud, longitud))

def yoLeft(user, latitud, longitud):
	left = database.query_db('SELECT yoleft FROM users WHERE name = "%s"' % (user))[0][0]
	if left > 0:
		database.query_db('UPDATE users SET yoleft = (yoleft - 1) WHERE name = "%s"' % user)
		database.query_db('UPDATE yoboard SET yo = (yo+1) WHERE name = "%s" AND latitud = %f AND longitud = %f' % (user, latitud, longitud))
		left -= 1
	return left

def top5(latitud, longitud):
	result = database.query_db('SELECT name FROM yoboard WHERE latitud = %f AND longitud = %f ORDER BY "yo" DESC LIMIT 5' % (latitud, longitud))
	ret = []
	i = 1
	for elem in result:
		ret.append("%d. %s" % (i,elem[0]))
		i += 1
	return ret

def rankNum(user, latitud, longitud):
	yos = database.query_db('SELECT yo FROM yoboard WHERE name ="%s"' % user)[0][0]
	return database.query_db('SELECT COUNT (*) FROM yoboard WHERE yo > %d AND longitud = %f AND latitud = %f' % (yos, latitud, longitud))[0][0] + 1

def getJackpot(latitud, longitud):
	return database.query_db('SELECT jackpot FROM locations WHERE latitud = %f AND longitud = %f' % (latitud, longitud))[0][0]
	
def addUser(user, latitud, longitud):
	database.query_db('INSERT INTO users VALUES ("%s", %d, %d, %f, %f)' % (user, TTL, inityoleft, latitud, longitud))

def getWinner1(latitud, longitud):
	return database.query_db('SELECT name FROM yoboard WHERE latitud = %f AND longitud = %f ORDER BY yo DESC LIMIT 1' % (latitud, longitud))[0][0]

def getWinner2(mat, suma):
	rand = randint(0,suma-1)
	for elem in mat:
		rand -= elem[1]
		if rand < 0:
			return elem[0]

def announcePrize():
	loc = database.query_db('SELECT latitud, longitud FROM locations')
	for elem in loc:
		mat = database.query_db('SELECT name, yo FROM yoboard WHERE latitud = %f AND longitud = %f' % (elem[0], elem[1]))
		suma = database.query_db('SELECT SUM(yo) FROM yoboard WHERE latitud = %f AND longitud = %f' % (elem[0], elem[1]))[0][0]
		win1 = getWinner1(elem[0], elem[1])
		win2 = getWinner2(mat, suma)
		jack = getJackpot(elem[0], elem[1])
		url = MAIN_URL + "/winner/" + str(jack/2) + "_" + str(win1) + "_" + str(win2)
		for person in mat:
			requests.post("http://api.justyo.co/yo/", data={'api_token': api_token, 'username': person[0], 'link': url})
		#database.query_db('UPDATE yoboard SET yo = %d' % inityo)

def giveFreePoints():
	database.query_db('UPDATE users SET yoleft = %d' % inityoleft)

schedule.every().day.at("00:00").do(giveFreePoints)
schedule.every().monday.do(announcePrize)

@app.route("/payment/", methods=['POST'])
def payment():
	yolos = request.POST["yolos"]
	username = request.POST["username"]
	database.query_db('UPDATE yoboard SET yoleft = yoleft + %d WHERE name = "%s"' %(yolos,username))
	css = url_for('static',filename='css/bootstrap.css')
	return render_template('purchase.html', s=css, name=username)

@app.route("/", methods=['GET'])
def yo_reciption():
	username = request.args.get('username')
	location = request.args.get('location')
	if type(location) == str:
		splitted = location.split(';')
		longitud = float("%.2f" % float(splitted[0]))
		latitud = float("%.2f" % float(splitted[1]))
		if existsUser(username):
			if not existsLocation(latitud, longitud):
				insertLocation(latitud, longitud)
			if not existsYoBoard(username, latitud, longitud):
				insertYoBoard(username, latitud, longitud)
			updateTTLs(username, latitud, longitud)
			left = yoLeft(username, latitud, longitud)
			rank = rankNum(username, latitud, longitud)
			top = top5(latitud, longitud)
			j = getJackpot(latitud, longitud)
			encoded = encodeURL(left, rank, j, top, username)
			encoded = MAIN_URL + url_for('rank', value=encoded)
			requests.post("http://api.justyo.co/yo/", data={'api_token': api_token, 'username': username, 'link': encoded})
		else:
			addUser(username, latitud, longitud)
	return 'OK'

@app.route('/rank/')
@app.route('/rank/<value>')
def rank(value=None):
	#value == None?
	yoleft,rank,prize,name,top = decodeURL(value)
	css = url_for('static',filename='css/bootstrap.css')
	return render_template('rank.html', yoleft=yoleft, rank=rank, prize=prize, top=top, name=name, s = css)

@app.route('/winner/<wolo>')
def winPage(wolo=None):
	aux = wolo.split('_')
	css = url_for('static',filename='css/bootstrap.css')
	print ("Winners are", aux[1:])
	return render_template('winner.html', winners=aux[1:], prize=aux[0], s = css)

if __name__ == "__main__":
	app.run(debug=True)
	