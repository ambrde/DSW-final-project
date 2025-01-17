from flask import Flask, redirect, url_for, session, request, jsonify, render_template, flash, Markup
from flask_apscheduler import APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from flask_oauthlib.client import OAuth
from bson.objectid import ObjectId

import pprint
import os
import time
import pymongo
import sys
import json
 
app = Flask(__name__)

#initialize scheduler with your preferred timezone
# scheduler = BackgroundScheduler({'apscheduler.timezone': 'America/Los_Angeles'})
# scheduler.start()
 
app.secret_key = os.environ['SECRET_KEY'] #used to sign session cookies
oauth = OAuth(app)
oauth.init_app(app) #initialize the app to be able to make requests for user information

#Set up GitHub as OAuth provider
github = oauth.remote_app(
    'github',
    consumer_key=os.environ['GITHUB_CLIENT_ID'], #your web app's "username" for github's OAuth
    consumer_secret=os.environ['GITHUB_CLIENT_SECRET'],#your web app's "password" for github's OAuth
    request_token_params={'scope': 'user:email'}, #request read-only access to the user's email.  For a list of possible scopes, see developer.github.com/apps/building-oauth-apps/scopes-for-oauth-apps
    base_url='https://api.github.com/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://github.com/login/oauth/access_token',  
    authorize_url='https://github.com/login/oauth/authorize' #URL for github's OAuth login
)

#Connect to database
url = os.environ["MONGO_CONNECTION_STRING"]
client = pymongo.MongoClient(url)
db = client[os.environ["MONGO_DBNAME"]]
collection = db['artpieces'] #TODO: put the name of the collection here

#context processors run before templates are rendered and add variable(s) to the template's context
#context processors must return a dictionary 
#this context processor adds the variable logged_in to the conext for all templates
@app.context_processor
def inject_logged_in():
    return {"logged_in":('github_token' in session)}

# #redirect to GitHub's OAuth page and confirm callback URL
@app.route('/login')
def login():   
    return github.authorize(callback=url_for('authorized', _external=True, _scheme='http')) #callback URL must match the pre-configured callback URL

@app.route('/logout')
def logout():
    session.clear()
    flash('You were logged out.')
    return redirect('/')

@app.route('/login/authorized')
def authorized():
    resp = github.authorized_response()
    if resp is None:
        session.clear()
        flash('Access denied: reason=' + request.args['error'] + ' error=' + request.args['error_description'] + ' full=' + pprint.pformat(request.args), 'error')      
    else:
        try:
            session['github_token'] = (resp['access_token'], '') #save the token to prove that the user logged in
            session['user_data']=github.get('user').data
            if session['user_data']['login'] not in collection.find():
                doc = {"username": session['user_data']['login'], "favorites": []}
                collection.insert_one(doc)
            flash('You were successfully logged in as ' + session['user_data']['login'] + '.')
        except Exception as inst:
            session.clear()
            print(inst)
            flash('Unable to login, please try again.', 'error')
    return redirect('/')


@app.route('/')
def renderHome():
    with open("artdata.json") as art_data:
        data = json.load(art_data)
    pieces = get_each(data)
    modals = get_modal(data)
    return render_template('page1.html', pieces=get_each(data), modals=get_modal(data))

@app.route('/your-favorites')
def renderPage2():
    with open("artdata.json") as art_data:
        data = json.load(art_data)
    favorites = get_favorites(data)
    modals = get_modal(data)
    return render_template('page2.html', favcount=favorites[0], favorites=favorites[1], modals=get_modal(data))
    
@app.route('/search-results')
def renderResults():
    with open("artdata.json") as art_data:
        data = json.load(art_data)
    results = get_search_results(data)
    searchterm = str(request.args['searchterm'])
    modals = get_modal(data)
    return render_template('search-results.html', count=results[0], results=results[1], searchterm = str(request.args['searchterm']), modals=get_modal(data))

@app.route("/favorite", methods = ["GET", "POST"])    
def add_favorite():
    print(list(request.form.keys())[0])
    contentId = list(request.form.keys())[0]
    doc = {"$push": {"favorites": contentId}}
    collection.update_one({"username": session['user_data']['login']}, doc)
    flash("Added to favorites")
    return redirect(request.referrer)

@app.route("/removefavorite", methods = ["GET", "POST"])
def remove_favorite():
    print(list(request.form.keys())[0])
    contentId = list(request.form.keys())[0]
    rdoc = {"$pull": {"favorites": contentId}}
    collection.update_one({"username": session['user_data']['login']}, rdoc)
    flash("Removed from favorites")
    return redirect(request.referrer)
     
def get_each(data):
    pieces = ""
    for p in data:
        title = p["title"]
        address = p["image"]
        artist = p["artistName"]
        contentId = p["contentId"]
        modalid = "c" + str(p["contentId"])
        pieces += Markup("<div class=\"col-sm-4 col-md-3 col-lg-2 col-xxl-1 container\"><img src=\"" + address + "\"" + "alt=\"" + title + "\"" + "class=\"image\" data-bs-toggle=\"modal\" data-bs-target=\"#" + modalid + "\"><div class=\"text\">" + title + "</div></div>")
    return pieces    
   
def get_modal(data):
    modals = ""
    for p in data:
        title = p["title"]
        address = p["image"]
        artist = p["artistName"]
        year = p["yearAsString"]
        contentId = p["contentId"]
        modalid = "c" + str(p["contentId"])
        modals += Markup("<div class=\"modal\" id=\"" + modalid + "\"><div class=\"modal-dialog modal-dialog-centered modal-xl\"><div class=\"modal-content\"><div class=\"modal-header\"><button type=\"button\" class=\"btn-close\" data-bs-dismiss=\"modal\"></button></div><div class=\"modal-body\"><img src=\"" + address + "\" class=\"img-fluid\"" + "alt=\"" + title + "\"><br><p>" + title + "<br>" + artist + "<br>" + year + "</p><span><form action=\"/favorite\" method=\"post\"><button class=\"far fa-heart right\" class=\"fas fa-heart right\" id=\"contentId\" name=\"" + str(contentId) + "\"></button></form><form action=\"/removefavorite\" method=\"post\"><button class=\"right\" id=\"contentId\" name=\"" + str(contentId) + "\">remove</button></form> </span></div></div></div></div>")
    return modals
    
def get_search_results(data):
    count = 0
    results = ""
    # modalid = ""
    searchterm = str(request.args['searchterm'])
    for p in data:
        modalid = "c" + str(p["contentId"])
        if searchterm.lower() in p["title"].lower() or searchterm.lower() in p["artistName"].lower():
            count = count + 1
            results += Markup("<div class=\"col-sm-4 col-md-3 col-lg-2 col-xxl-1 container\"><img src=\"" + p["image"] + "\"" + "alt=\"" + p["title"] + "\"" + "class=\"image\" data-bs-toggle=\"modal\" data-bs-target=\"#" + modalid + "\"><div class=\"text\">" + p["title"] + "</div></div>")
    return count, results
   
def get_favorites(data):
    favcount = 0
    favorites = ""
    # removefavorite = ""
    # contentId = list(request.form.keys())[0]
    document = collection.find_one({"username": session['user_data']['login']})
    print(document)
    for p in data:
        modalid = "c" + str(p["contentId"])
        if str(p["contentId"]) in document['favorites']:
            favcount = favcount + 1
            favorites += Markup("<div class=\"col-sm-4 col-md-3 col-lg-2 col-xxl-1 container\"><img src=\"" + p["image"] + "\"" + "alt=\"" + p["title"] + "\"" + "class=\"image\" data-bs-toggle=\"modal\" data-bs-target=\"#" + modalid + "\"><div class=\"text\">" + p["title"] + "</div></div>")
            ## removefavorite += Markup("<form action=\"/removefavorite\" method=\"post\"><button id=\"contentId\" name=\"" + str(contentId) + "\"></button></form>")
    print(favcount)
    return favcount, favorites

#the tokengetter is automatically called to check who is logged in.
@github.tokengetter
def get_github_oauth_token():
    return session['github_token']


if __name__ == '__main__':
    app.run(debug=True)
