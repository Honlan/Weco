# coding:utf-8

# 加载需要使用的包
import sys
reload(sys)
sys.setdefaultencoding( "utf-8" )
import os
import base64
from flask import *
import MySQLdb
import MySQLdb.cursors
import json
from hashlib import md5
import random
import smtplib  
from email.mime.text import MIMEText
import time
import warnings
warnings.filterwarnings("ignore")
from werkzeug import secure_filename
import math
import pprint

# 加载配置文件
from conf.configure import *

# 载入系统配置
app = Flask(__name__)
app.config.from_object(__name__)
app.secret_key="8E9852FD04BA946D51DE36DFB08E1DB6"

# 数据库连接
db = MySQLdb.connect(host=HOST, user=USER, passwd=PASSWORD, db=DATABASE, port=PORT, charset=CHARSET, cursorclass = MySQLdb.cursors.DictCursor)
db.autocommit(True)
cursor = db.cursor()

# 加载其他模块代码
import weco.api.user

'''
	动态类别说明：
	1. 其他用户关注了我
	2. 其他用户喜欢了我的创意
	3. 其他用户评论了我的创意
'''

'''
	api部分
'''

# 验证token是否属于用户并检测是否有效
def validate(username, token):
	count = cursor.execute("select lastActive, TTL from user where username = %s and token = %s", [username, token])
	if count == 0:
		return False
	else:
		user = cursor.fetchone()
		lastActive = user['lastActive']
		TTL = user['TTL']
		interval = 3600*24*7
		if int(time.time()) - int(lastActive) > interval or TTL < 1:
			return False
		else:
			TTL = TTL - 1
			cursor.execute("update user set TTL = %s where username = %s", [str(TTL), username])
			return True



# 判断邮箱是否存在
@app.route('/api/user/existEmail', methods=['POST'])
def api_user_exist_email():
	data = request.form
	count = cursor.execute("select email from user where email = %s", [data['email']])
	if count > 0:
		return json.dumps({"ok": True, "exist": True})
	else:
		return json.dumps({"ok": True, "exist": False})

# 根据offset获取热门创意
@app.route('/api/idea/hot', methods=['POST'])
def api_idea_hot():
	offset = int(request.form['offset'])
	cursor.execute('select * from idea where locked=0 order by praise desc, timestamp desc limit ' + str(offset*10) + ',10')
	ideas = cursor.fetchall()
	for item in ideas:
		temp = int(time.time()) - int(item['timestamp'])
		if temp < 60:
			temp = str(temp) + 's'
		elif temp < 3600:
			temp = str(temp/60) + 'm'
		elif temp < 3600 * 24:
			temp = str(temp/3600) + 'h'
		else:
			temp = str(temp/(3600*24)) + 'd'
		item['timestamp'] = temp
	return json.dumps({"ok": True, "ideas": ideas})

# 根据offset获取最新创意
@app.route('/api/idea/latest', methods=['POST'])
def api_idea_latest():
	offset = int(request.form['offset'])
	cursor.execute('select * from idea where locked=0 order by timestamp desc, praise desc limit ' + str(offset*10) + ',10')
	ideas = cursor.fetchall()
	for item in ideas:
		temp = int(time.time()) - int(item['timestamp'])
		if temp < 60:
			temp = str(temp) + 's'
		elif temp < 3600:
			temp = str(temp/60) + 'm'
		elif temp < 3600 * 24:
			temp = str(temp/3600) + 'h'
		else:
			temp = str(temp/(3600*24)) + 'd'
		item['timestamp'] = temp
	return json.dumps({"ok": True, "ideas": ideas})

# 用户关注创意
# 需要进行token验证
@app.route('/api/idea/follow', methods=['POST'])
def api_idea_follow():
	data = request.form
	if validate(data['username'], data['token']):
		ideaId = data['ideaId']
		username = data['username']
		cursor.execute("select nickname,followIdeas from user where username = %s", [username])
		nickname = cursor.fetchone()
		followIdeas = nickname['followIdeas']
		nickname = nickname['nickname']
		followIdeas = followIdeas.split(',')
		if not ideaId in followIdeas:
			followIdeas.append(ideaId)
		temp = ''
		for item in followIdeas:
			if item == '':
				continue
			temp = temp + item + ','
		followIdeas = temp[:-1]
		cursor.execute("update user set followIdeas = %s where username = %s", [followIdeas, username])
		# 添加类别2动态，我的创意被别人关注了
		cursor.execute("select title,owner from idea where id=%s",[ideaId])
		owner = cursor.fetchone()
		ideaTitle = owner['title']
		owner = owner['owner']
		cursor.execute("insert into activity(me,other,otherNickname,ideaId,ideaTitle,activityType,timestamp) values(%s,%s,%s,%s,%s,%s,%s)",[owner,username,nickname,ideaId,ideaTitle,2,str(int(time.time()))])
		return json.dumps({"ok": True})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 用户取消关注创意
# 需要进行token验证
@app.route('/api/idea/disfollow', methods=['POST'])
def api_idea_disfollow():
	data = request.form
	if validate(data['username'], data['token']):
		ideaId = data['ideaId']
		username = data['username']
		cursor.execute("select followIdeas from user where username = %s", [username])
		followIdeas = cursor.fetchone()['followIdeas']
		followIdeas = followIdeas.split(',')
		if ideaId in followIdeas:
			followIdeas.remove(ideaId)
		temp = ''
		for item in followIdeas:
			if item == '':
				continue
			temp = temp + item + ','
		followIdeas = temp[:-1]
		cursor.execute("update user set followIdeas = %s where username = %s", [followIdeas, username])
		return json.dumps({"ok": True})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 用户点赞创意
@app.route('/api/idea/praise', methods=['POST'])
def api_idea_praise():
	ideaId = request.form['ideaId']
	if (not session.get('ideas') == None) and (not session['ideas'].get(str(ideaId)) == None):
		if session['ideas'][str(ideaId)] == 0:
			# 点赞
			cursor.execute('select praise from idea where id=%s', [ideaId])
			praise = int(cursor.fetchone()['praise']) + 1
			cursor.execute('update idea set praise=%s where id=%s', [praise,ideaId])
			session['ideas'][str(ideaId)] = 1
			return json.dumps({"ok": True, "praise": praise, "action": "increase"})
		else:
			# 取消赞
			cursor.execute('select praise from idea where id=%s', [ideaId])
			praise = int(cursor.fetchone()['praise']) - 1
			cursor.execute('update idea set praise=%s where id=%s', [praise,ideaId])
			session['ideas'][str(ideaId)] = 0
			return json.dumps({"ok": True, "praise": praise, "action": "decrease"})
	else:
		return json.dumps({"ok": False})

# 用户点赞评论
@app.route('/api/comment/praise', methods=['POST'])
def api_comment_praise():
	commentId = request.form['commentId']
	if session.get('comments') == None:
		session['comments'] = {}
	if session['comments'].get(str(commentId)) == None:
		# 点赞评论
		session['comments'][str(commentId)] = True
		cursor.execute('select praise from comment where id=%s', [commentId])
		praise = int(cursor.fetchone()['praise']) + 1
		cursor.execute('update comment set praise=%s where id=%s', [praise,commentId])
		return json.dumps({"ok": True, "praise": praise, "action": "increase"})
	else:
		# 取消赞评论
		session['comments'].pop(str(commentId), None)
		cursor.execute('select praise from comment where id=%s', [commentId])
		praise = int(cursor.fetchone()['praise']) - 1
		cursor.execute('update comment set praise=%s where id=%s', [praise,commentId])
		return json.dumps({"ok": True, "praise": praise, "action": "decrease"})

# 为创意添加图片内容
# 需要进行token验证
@app.route('/api/idea/addImg', methods=['POST'])
def api_idea_addImg():
	data = request.form
	if validate(data['username'], data['token']):
		ideaId = data['ideaId']
		cursor.execute("select owner from idea where id=%s",[ideaId])
		if cursor.fetchone()['owner'] == data['username']:
			imgBase = data['image']
			imgBase = imgBase[imgBase.find('base64')+7:]
			imageData = base64.b64decode(imgBase)
			today = time.strftime('%Y%m%d%H', time.localtime(time.time()))
			filename = today + '_' + genKey()[:10] + '.jpg'
			UPLOAD_FOLDER = '/static/uploads/img'
			filepath = os.path.join(WECOROOT + UPLOAD_FOLDER, filename)
			relapath = os.path.join(UPLOAD_FOLDER, filename)
			imageFile = open(filepath,'wb')
			imageFile.write(imageData)
			imageFile.close()
			cursor.execute("insert into attachment(ideaId,fileType,url,timestamp,username) values(%s,%s,%s,%s,%s)",[ideaId,1,relapath,str(int(time.time())), data['username']])
			return json.dumps({"ok": True})
		else:
			return json.dumps({"ok": False, "error": "invalid token"})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 删除创意附件
# 需要进行token验证
@app.route('/api/attachment/remove',methods=['POST'])
def api_attachment_remove():
	data = request.form
	if validate(data['username'], data['token']):
		attachmentId = data['attachmentId']
		cursor.execute("select * from attachment where id=%s",[attachmentId])
		attachment = cursor.fetchone()
		if attachment['username'] == data['username']:
			if (not attachment['fileType'] == 0) and (os.path.exists(WECOROOT + attachment['url'])):
				os.remove(WECOROOT + attachment['url'])
			cursor.execute('delete from attachment where id=%s', [attachmentId])
			return json.dumps({"ok": True})
		else:
			return json.dumps({"ok": False, "error": "invalid token"})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 编辑创意
# 需要进行token验证
@app.route('/api/idea/edit', methods=['POST'])
def api_idea_edit():
	data = request.form
	if validate(data['username'], data['token']):
		ideaId = data['ideaId']
		cursor.execute("select owner from idea where id=%s",[ideaId])

		# 创意确实属于用户
		if cursor.fetchone()['owner'] == data['username']:
			cursor.execute("update idea set title=%s,tags=%s,category=%s where id=%s",[data['title'],data['tags'],data['category'],ideaId])
			
			# 统计创意tag次数
			for tag in data['tags'].split(' '):
				if tag == '':
					continue
				cursor.execute("select count from ideaTagStat where tag=%s and category=%s",[tag,data['category']])
				record = cursor.fetchone()
				if record == None:
					cursor.execute("insert into ideaTagStat(tag,category,count) values(%s,%s,1)",[tag,data['category']])
				else:
					count = int(record['count']) + 1
					cursor.execute("update ideaTagStat set count=%s where tag=%s and category=%s",[count,tag,data['category']])
			
			# 处理创意缩略图
			if data.has_key('thumbnail'):
				imgBase = data['thumbnail']
				imgBase = imgBase[imgBase.find('base64')+7:]
				imageData = base64.b64decode(imgBase)
				today = time.strftime('%Y%m%d%H', time.localtime(time.time()))
				filename = today + '_' + genKey()[:10] + '.jpg'
				UPLOAD_FOLDER = '/static/uploads/img'
				filepath = os.path.join(WECOROOT + UPLOAD_FOLDER, filename)
				relapath = os.path.join(UPLOAD_FOLDER, filename)
				imageFile = open(filepath,'wb')
				imageFile.write(imageData)
				imageFile.close()

				# 删除旧缩略图并更新新缩略图路径
				cursor.execute('select thumbnail from idea where id=%s',[ideaId])
				oldthumb = cursor.fetchone()['thumbnail']
				if (not oldthumb == '/static/img/idea.jpg') and (os.path.exists(WECOROOT + oldthumb)):
					os.remove(WECOROOT + oldthumb)
				cursor.execute("update idea set thumbnail=%s where id=%s",[relapath,ideaId])
			return json.dumps({"ok": True})

		# 创意不属于该用户
		else:
			return json.dumps({"ok": False, "error": "invalid token"})
	
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 用户评论创意
# 需要进行token验证
@app.route('/api/idea/comment', methods=['POST'])
def api_idea_comment():
	data = request.form
	if validate(data['username'], data['token']):
		ideaId = data['ideaId']
		username = data['username']
		timestamp = str(int(time.time()))
		content = data['content']
		cursor.execute('select nickname,portrait from user where username=%s', [username])
		nickname = cursor.fetchone()
		portrait = nickname['portrait']
		nickname = nickname['nickname']

		# 新增评论记录
		cursor.execute("insert into comment(username,nickname,portrait,ideaId,timestamp,content) values(%s,%s,%s,%s,%s,%s)", [username,nickname,portrait,ideaId,timestamp,content])
		cursor.execute("select commentCount from idea where id=%s",[ideaId])
		commentCount = int(cursor.fetchone()['commentCount']) + 1
		cursor.execute("update idea set commentCount=%s where id=%s",[commentCount,ideaId])
		
		# 添加类别3动态，我的创意被别人评论了
		cursor.execute("select title,owner from idea where id=%s",[ideaId])
		owner = cursor.fetchone()
		ideaTitle = owner['title']
		owner = owner['owner']
		cursor.execute("insert into activity(me,other,otherNickname,ideaId,ideaTitle,comment,activityType,timestamp) values(%s,%s,%s,%s,%s,%s,%s,%s)",[owner,username,nickname,ideaId,ideaTitle,content,3,str(int(time.time()))])
		return json.dumps({"ok": True})
	
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 用户编辑个人信息
# 需要进行token验证
@app.route('/api/user/edit', methods=['POST'])
def api_user_edit():
	data = request.form
	if validate(data['username'], data['token']):
		nickname = data['nickname']
		gender = data['gender']
		tags = data['tags']
		description = data['description']
		email = data['email']
		wechat = data['wechat']

		# 统计用户tag次数
		for tag in tags.split(' '):
			if tag == '':
				continue
			cursor.execute("select count from userTagStat where tag=%s and gender=%s",[tag,gender])
			record = cursor.fetchone()
			if record == None:
				cursor.execute("insert into userTagStat(tag,gender,count) values(%s,%s,1)",[tag,gender])
			else:
				count = int(record['count']) + 1
				cursor.execute("update userTagStat set count=%s where tag=%s and gender=%s",[count,tag,gender])
		
		cursor.execute("update user set nickname=%s, gender=%s,tags=%s,description=%s,email=%s,wechat=%s where username=%s", [nickname,gender,tags,description,email,wechat,data['username']])
		# 处理用户头像
		if data.has_key('portrait'):
			portrait = data['portrait']
			portrait = portrait[portrait.find('base64')+7:]
			imageData = base64.b64decode(portrait)
			today = time.strftime('%Y%m%d%H', time.localtime(time.time()))
			filename = today + '_' + genKey()[:10] + '.jpg'
			UPLOAD_FOLDER = '/static/uploads/img'
			filepath = os.path.join(WECOROOT + UPLOAD_FOLDER, filename)
			relapath = os.path.join(UPLOAD_FOLDER, filename)
			imageFile = open(filepath,'wb')
			imageFile.write(imageData)
			imageFile.close()
			cursor.execute('select portrait from user where username=%s',[data['username']])
			oldportrait = cursor.fetchone()['portrait']
			if (not oldportrait == '/static/img/user.png') and (os.path.exists(WECOROOT + oldportrait)):
				os.remove(WECOROOT + oldportrait)
			cursor.execute("update user set portrait=%s where username=%s",[relapath,data['username']])
			cursor.execute("select ideas from user where username=%s",[data['username']])
			myIdeas = cursor.fetchone()['ideas'].split(',')
			for item in myIdeas:
				cursor.execute("update idea set portrait=%s where id=%s",[relapath,item])
		return json.dumps({"ok": True})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 用户关注其他用户
# 需要进行token验证
@app.route('/api/user/follow', methods=['POST'])
def api_user_follow():
	data = request.form
	if validate(data['source'], data['token']):
		source = data['source']
		target = data['target']
		cursor.execute("select nickname,followUsers from user where username = %s", [source])
		nickname = cursor.fetchone()
		followUsers = nickname['followUsers']
		nickname = nickname['nickname']
		followUsers = followUsers.split(',')
		if not target in followUsers:
			followUsers.append(target)
		temp = ''
		for item in followUsers:
			if item == '':
				continue
			temp = temp + item + ','
		followUsers = temp[:-1]
		cursor.execute("update user set followUsers = %s where username = %s", [followUsers, source])
		cursor.execute("select fans from user where username = %s", [target])
		fans = cursor.fetchone()['fans']
		fans = fans.split(',')
		if not source in fans:
			fans.append(source)
		temp = ''
		for item in fans:
			if item == '':
				continue
			temp = temp + item + ','
		fans = temp[:-1]
		cursor.execute("update user set fans = %s where username = %s", [fans, target])
		# 添加类别1动态，我被别人关注了
		cursor.execute("insert into activity(me,other,otherNickname,activityType,timestamp) values(%s,%s,%s,%s,%s)",[target,source,nickname,1,str(int(time.time()))])
		return json.dumps({"ok": True})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 用户取消关注其他用户
# 需要进行token验证
@app.route('/api/user/disfollow', methods=['POST'])
def api_user_disfollow():
	data = request.form
	if validate(data['source'], data['token']):
		source = data['source']
		target = data['target']
		cursor.execute("select followUsers from user where username = %s", [source])
		followUsers = cursor.fetchone()['followUsers']
		followUsers = followUsers.split(',')
		if target in followUsers:
			followUsers.remove(target)
		temp = ''
		for item in followUsers:
			if item == '':
				continue
			temp = temp + item + ','
		followUsers = temp[:-1]
		cursor.execute("update user set followUsers = %s where username = %s", [followUsers, source])
		cursor.execute("select fans from user where username = %s", [target])
		fans = cursor.fetchone()['fans']
		fans = fans.split(',')
		if source in fans:
			fans.remove(source)
		temp = ''
		for item in fans:
			if item == '':
				continue
			temp = temp + item + ','
		fans = temp[:-1]
		cursor.execute("update user set fans = %s where username = %s", [fans, target])
		return json.dumps({"ok": True})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 发送聊天消息
# 需要进行token验证
@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
	data = request.form
	if validate(data['source'], data['token']):
		source = data['source']
		target = data['target']
		content = data['content']
		timestamp = str(int(time.time()))
		cursor.execute("select nickname from user where username=%s",[target])
		targetNickname = cursor.fetchone()['nickname']
		cursor.execute("select nickname from user where username=%s",[source])
		sourceNickname = cursor.fetchone()['nickname']
		cursor.execute("insert into chat(source,sourceNickname,target,targetNickname,content,timestamp) values(%s,%s,%s,%s,%s,%s)",[source,sourceNickname,target,targetNickname,content,timestamp])
		return json.dumps({"ok": True})
	else:
		return json.dumps({"ok": False, "error": "invalid token"})

# 随机码生成器
def genKey():
	key = ''
	for x in xrange(0, 10):
		key = key + str(random.randint(0, 9))
	key = unicode(md5(key + str(int(time.time()))).hexdigest().upper())
	return key

# 存储当前页面
@app.route('/storeCurrentUrl',methods=['POST'])
def storeCurrentUrl():
	session['url'] = request.form['url']
	return json.dumps({"ok": True})

# 主页，展示热门创意
@app.route('/')
def index():
	cursor.execute('select * from idea where locked=0 order by praise desc, timestamp desc limit 10')

	# 转换时间戳
	ideas = cursor.fetchall()
	for item in ideas:
		temp = int(time.time()) - int(item['timestamp'])
		if temp < 60:
			temp = str(temp) + 's'
		elif temp < 3600:
			temp = str(temp/60) + 'm'
		elif temp < 3600 * 24:
			temp = str(temp/3600) + 'h'
		else:
			temp = str(temp/(3600*24)) + 'd'
		item['timestamp'] = temp

	return render_template('index/index.html', ideas=ideas, hot=True)
		

# 主页，展示最新创意
@app.route('/<mode>')
def index_latest(mode):
	if mode == 'latest':
		cursor.execute('select * from idea where locked=0 order by timestamp desc, praise desc limit 10')

		# 转换时间戳
		ideas = cursor.fetchall()
		for item in ideas:
			temp = int(time.time()) - int(item['timestamp'])
			if temp < 60:
				temp = str(temp) + 's'
			elif temp < 3600:
				temp = str(temp/60) + 'm'
			elif temp < 3600 * 24:
				temp = str(temp/3600) + 'h'
			else:
				temp = str(temp/(3600*24)) + 'd'
			item['timestamp'] = temp

		return render_template('index/index.html', ideas=ideas, hot=False)

# 我的主页
@app.route('/user')
def home():
	if not session.get('username') == None:
		# 用户已登陆
		cursor.execute('select * from user where username=%s', [session.get('username')])
		user = cursor.fetchone()

		# 获取所关注的其他用户名单
		followUserStr = user['followUsers']

		# 获取热门标签以供编辑
		hotTags = {}
		cursor.execute("select tag from userTagStat where gender=1 order by count desc limit 10")
		hotTags['male'] = cursor.fetchall()
		cursor.execute("select tag from userTagStat where gender=0 order by count desc limit 10")
		hotTags['female'] = cursor.fetchall()

		# 获取用户的创意
		ideas = user['ideas']
		ideasCount = 0
		if not ideas == '':
			cursor.execute('select id,title,thumbnail from idea where id in (%s) and locked=0' % (ideas))
			ideas = cursor.fetchall()
			ideasCount = len(ideas)
		else:
			ideas = None

		# 获取用户喜欢的创意
		followIdeas = user['followIdeas']
		followIdeasCount = 0
		if not followIdeas == '':
			cursor.execute('select id,title,thumbnail from idea where id in (%s) and locked=0' % (followIdeas))
			followIdeas = cursor.fetchall()
			followIdeasCount = len(followIdeas)
		else:
			followIdeas = None

		# 获取用户关注的其他用户
		followUsers = user['followUsers']
		followUsersCount = 0
		if not followUsers == '':
			followUsers = followUsers.split(',')
			temp = ''
			for item in followUsers:
				temp = temp + '"' + item + '",'
			followUsers = temp[:-1]
			cursor.execute('select username,nickname,portrait,fans from user where username in (%s)' % (followUsers))
			followUsers = cursor.fetchall()
			for item in followUsers:
				temp = item['fans']
				if temp == '':
					temp = 0
				else:
					temp = len(temp.split(','))
				item['fans'] = temp
			followUsersCount = len(followUsers)
		else:
			followUsers = None

		# 获取用户的粉丝
		fans = user['fans']
		fansCount = 0
		if not fans == '':
			fans = fans.split(',')
			temp = ''
			for item in fans:
				temp = temp + '"' + item + '",'
			fans = temp[:-1]
			cursor.execute('select username,nickname,portrait,fans from user where username in (%s)' % (fans))
			fans = cursor.fetchall()
			for item in fans:
				temp = item['fans']
				if temp == '':
					temp = 0
				else:
					temp = len(temp.split(','))
				item['fans'] = temp
			fansCount = len(fans)
		else:
			fans = None

		return render_template('user/home.html', user=user, ideas=ideas, ideasCount=ideasCount, followIdeas=followIdeas, followIdeasCount=followIdeasCount, followUsers=followUsers, followUsersCount=followUsersCount, fans=fans, fansCount=fansCount, followUserStr=followUserStr, hotTags=hotTags)
	else:
		# 访问个人主页前需登录
		return redirect(url_for('login'))

# 其他用户主页
@app.route('/user/<username>')
def user(username):
	if session.get('username') == username:
		# 访问的就是本人，返回个人主页
		return redirect(url_for('home'))

	else:
		# 访问其他用户
		cursor.execute('select username,email,nickname,portrait,tags,description,gender,wechat,ideas,followIdeas,fans,followUsers,lastActive from user where username=%s',[username])
		user = cursor.fetchone()

		# 获取其他用户的创意
		ideas = user['ideas']
		ideasCount = 0
		if not ideas == '':
			cursor.execute('select id,title,thumbnail from idea where id in (%s) and locked=0' % (str(ideas)))
			ideas = cursor.fetchall()
			ideasCount = len(ideas)
		else:
			ideas = None

		# 获取其他用户喜欢的创意
		followIdeas = user['followIdeas']
		followIdeasCount = 0
		if not followIdeas == '':
			cursor.execute('select id,title,thumbnail from idea where id in (%s) and locked=0' % (str(followIdeas)))
			followIdeas = cursor.fetchall()
			followIdeasCount = len(followIdeas)
		else:
			followIdeas = None

		# 获取其他用户的关注
		followUsers = user['followUsers']
		followUsersCount = 0
		if not followUsers == '':
			followUsers = followUsers.split(',')
			temp = ''
			for item in followUsers:
				temp = temp + '"' + item + '",'
			followUsers = temp[:-1]
			cursor.execute('select username,nickname,portrait,fans from user where username in (%s)' % (followUsers))
			followUsers = cursor.fetchall()
			for item in followUsers:
				temp = item['fans']
				if temp == '':
					temp = 0
				else:
					temp = len(temp.split(','))
				item['fans'] = temp
			followUsersCount = len(followUsers)
		else:
			followUsers = None

		# 获取其他用户的粉丝
		fans = user['fans']
		fansCount = 0
		if not fans == '':
			fans = fans.split(',')
			temp = ''
			for item in fans:
				temp = temp + '"' + item + '",'
			fans = temp[:-1]
			cursor.execute('select username,nickname,portrait,fans from user where username in (%s)' % (fans))
			fans = cursor.fetchall()
			for item in fans:
				temp = item['fans']
				if temp == '':
					temp = 0
				else:
					temp = len(temp.split(','))
				item['fans'] = temp
			fansCount = len(fans)
		else:
			fans = None

		# 获取当前用户的关注列表
		followUserStr = ''
		me = session.get('username')
		if not me == None:
			cursor.execute('select followUsers from user where username=%s',[me])
			followUserStr = cursor.fetchone()['followUsers']

		return render_template('user/user.html',user=user, ideas=ideas, ideasCount=ideasCount, followIdeas=followIdeas, followIdeasCount=followIdeasCount, followUsers=followUsers, followUsersCount=followUsersCount, fans=fans, fansCount=fansCount, followUserStr=followUserStr)

# 发布创意
@app.route('/idea/new',methods=['GET','POST'])
def idea_new():
	if request.method == 'GET':
		# 用户已经登陆
		if not session.get('username') == None:
			# 获取热门标签
			category = ['社会','设计','生活','城市','娱乐','健康','旅行','教育','运动','产品','艺术','科技','工程','广告','其他']
			hotTags = {}
			for item in category:
				cursor.execute("select tag from ideaTagStat where category=%s order by count desc limit 10",[item])
				hotTags[item] = cursor.fetchall()

			return render_template('idea/idea_new.html',hotTags=hotTags)

		# 用户尚未登录
		else:
			return redirect(url_for('login'))

	elif request.method == 'POST':
		# 用户已经登陆
		if not session.get('username') == None:
			# 新增创意数据
			username = session.get('username')
			title = request.form['title']
			category = request.form['category']
			tags = request.form['tags']
			timestamp = str(int(time.time()))
			cursor.execute('select nickname from user where username=%s',[username])
			nickname = cursor.fetchone()['nickname']
			cursor.execute('insert into idea(title,category,tags,timestamp,owner,nickname) values(%s,%s,%s,%s,%s,%s)',[title,category,tags,timestamp,username,nickname])
			
			# 获取新增创意id
			cursor.execute('select id from idea where title=%s and category=%s and tags=%s and timestamp=%s and owner=%s and nickname=%s',[title,category,tags,timestamp,username,nickname])
			ideaId = cursor.fetchone()['id']

			# 将该id添加至用户的创意列表中
			cursor.execute('select ideas from user where username=%s',[username])
			ideas = cursor.fetchone()['ideas']
			ideas = ideas + ',' + str(ideaId)
			ideas = ideas.lstrip(',')
			cursor.execute('update user set ideas=%s where username=%s',[ideas,username])

			# 统计创意tag次数
			for tag in tags.split(' '):
				if tag == '':
					continue
				cursor.execute("select count from ideaTagStat where tag=%s and category=%s",[tag,category])
				record = cursor.fetchone()
				if record == None:
					cursor.execute("insert into ideaTagStat(tag,category,count) values(%s,%s,1)",[tag,category])
				else:
					count = int(record['count']) + 1
					cursor.execute("update ideaTagStat set count=%s where tag=%s and category=%s",[count,tag,category])
			return redirect(url_for('idea',ideaId=ideaId))

		# 用户尚未登录
		else:
			return redirect(url_for('login'))

# 创意主页
@app.route('/idea/<ideaId>')
def idea(ideaId):
	# 如果创意已被锁定，则给出错误提示
	# TO DO

	# 缓存该创意的阅读、点赞等用户行为
	if session.get('ideas') == None:
		session['ideas'] = {}

	# 阅读量＋1
	if not session['ideas'].has_key(str(ideaId)):
		cursor.execute('select readCount from idea where id=%s', [ideaId])
		readCount = int(cursor.fetchone()['readCount']) + 1
		cursor.execute('update idea set readCount=%s where id=%s', [readCount,ideaId])
		session['ideas'][str(ideaId)] = 0
	
	# 获取创意信息
	cursor.execute('select * from idea where id=%s', [ideaId])
	idea = cursor.fetchone()
	idea['timestamp'] = time.strftime('%m-%d %H:%M', time.localtime(float(idea['timestamp'])))

	# 判断当前用户是否已经喜欢该创意
	liked = False
	username = session.get('username')
	if (not username == None) and (not username == idea['owner']):
		cursor.execute('select followIdeas from user where username=%s',[username])
		if ideaId in cursor.fetchone()['followIdeas'].split(','):
			liked = True
		else:
			liked = False

	# 获取该创意所有附件
	cursor.execute("select * from attachment where ideaId=%s order by timestamp asc",[ideaId])
	attachments = cursor.fetchall()
	for item in attachments:
		item['timestamp'] = time.strftime('%m-%d %H:%M', time.localtime(float(item['timestamp'])))

	# 获取该创意所有评论
	cursor.execute("select * from comment where ideaId=%s order by praise desc, timestamp desc", [ideaId])
	comments = cursor.fetchall()
	for item in comments:
		item['timestamp'] = time.strftime('%m-%d %H:%M', time.localtime(float(item['timestamp'])))
	commentsCount = len(comments)
	
	# 获取该创意发起人粉丝人数
	cursor.execute("select fans from user where username=%s",[idea['owner']])
	fans = len(cursor.fetchone()['fans'].split(','))

	# 获取热门标签以供编辑
	category = ['社会','设计','生活','城市','娱乐','健康','旅行','教育','运动','产品','艺术','科技','工程','广告','其他']
	hotTags = {}
	for item in category:
		cursor.execute("select tag from ideaTagStat where category=%s order by count desc limit 10",[item])
		hotTags[item] = cursor.fetchall()

	return render_template('idea/idea.html', idea=idea, liked=liked, attachments=attachments, comments=comments, commentsCount=commentsCount, fans=fans, hotTags=hotTags)

# 为创意添加文本内容
@app.route('/idea/addText/<ideaId>',methods=['POST'])
def idea_add_text(ideaId):
	if not session.get('username') == None:
		text = request.form['content']
		cursor.execute("insert into attachment(ideaId,fileType,url,timestamp,username) values(%s,%s,%s,%s,%s)",[ideaId,0,text,str(int(time.time())), session.get('username')])
		return redirect(url_for('idea', ideaId=ideaId))
	else:
		return redirect(url_for('login'))

# 为创意添加视频内容
@app.route('/idea/addVideo/<ideaId>', methods=['POST'])
def idea_add_video(ideaId):
	if not session.get('username') == None:
		image = request.files['content']
		today = time.strftime('%Y%m%d', time.localtime(time.time()))
		filename = today + '_' + secure_filename(genKey()[:10] + '_' + image.filename)
		UPLOAD_FOLDER = '/static/uploads/video'
		filepath = os.path.join(WECOROOT + UPLOAD_FOLDER, filename)
		relapath = os.path.join(UPLOAD_FOLDER, filename)
		image.save(filepath)
		cursor.execute("insert into attachment(ideaId,fileType,url,timestamp,username) values(%s,%s,%s,%s,%s)",[ideaId,2,relapath,str(int(time.time())), session.get('username')])
		return redirect(url_for('idea', ideaId=ideaId))
	else:
		return redirect(url_for('login'))

# 搜索创意
@app.route('/search')
def search():
	recent = None
	hot = None

	if not session.get('username') == None:
		# 获取当前用户的最近搜索记录
		cursor.execute("select * from search where username=%s and keyword!='' group by keyword,target order by timestamp desc limit 10",[session.get('username')])
		recent = cursor.fetchall()
	
	# 获取热门搜索记录
	cursor.execute("select keyword, target, count(*) as count from search where timestamp > %s and keyword!='' group by keyword,target order by count(*) desc limit 10",[int(time.time())-3600*24*7])
	hot = cursor.fetchall();

	# 获取各个类别的创意数量
	cursor.execute("select count(id) as count, category from idea where locked=0 group by category")
	categoryStat = cursor.fetchall()
	temp = {}
	for item in categoryStat:
		temp[item['category']] = item['count']
	categoryStat = temp
	pprint.pprint(categoryStat)
	return render_template('search/search.html',recent=recent,hot=hot,categoryStat=categoryStat)

# 关键词搜索
@app.route('/search/keyword')
def search_keyword():
	target = request.args.get('target')
	keyword = request.args.get('keyword')
	key = keyword
	pageId = request.args.get('pageId')
	numPerPage = 10
	pageId = int(pageId)

	# 记录本次搜索
	keyword = keyword.split(' ')
	if session.get('username') == None:
		username = ''
	else:
		username = session.get('username')

	# 存储搜索结果
	result = []
	if target == 'idea':
		# 搜索的是创意
		for item in keyword:
			cursor.execute("insert into search(username,target,keyword,timestamp) values(%s,%s,%s,%s)",[username,target,item,str(int(time.time()))])
			cursor.execute("select * from idea where locked=0 and title like '%%%s%%' or tags like '%%%s%%' or category like '%%%s%%'" % (item,item,item))
			ideas = cursor.fetchall()
			for i in ideas:
				temp = int(time.time()) - int(i['timestamp'])
				if temp < 60:
					temp = str(temp) + 's'
				elif temp < 3600:
					temp = str(temp/60) + 'm'
				elif temp < 3600 * 24:
					temp = str(temp/3600) + 'h'
				else:
					temp = str(temp/(3600*24)) + 'd'
				i['timestamp'] = temp
				result.append(i)
		result = sorted(result, key=lambda x:(x['praise'], x['timestamp']), reverse=True)
	elif target == 'user': 
		# 搜索的是用户
		for item in keyword:
			cursor.execute("insert into search(username,target,keyword,timestamp) values(%s,%s,%s,%s)",[username,target,item,str(int(time.time()))])
			cursor.execute("select username,nickname,portrait,tags,description,fans,lastActive from user where nickname like '%%%s%%' or tags like '%%%s%%' or description like '%%%s%%'" % (item,item,item))
			users = cursor.fetchall()
			for i in users:
				if i['fans'] == '':
					i['fans'] = 0
				else:
					i['fans'] = len(i['fans'].split(','))
				pprint.pprint(i)
				result.append(i)
		result = sorted(result, key=lambda x:(x['lastActive']), reverse=True)

	# 计算分页信息，截取结果
	count = len(result)
	result = result[pageId*numPerPage:pageId*numPerPage+numPerPage]
	start = int(pageId) - 3
	end = int(pageId) + 3
	total = int(math.ceil(float(count) / numPerPage)) - 1
	if start < 0:
		start = 0
	if end > total:
		end = total
	pages = []
	for i in xrange(start, end + 1):
		pages.append(i)

	# 关键词搜索无返回结果时查看当前热门搜索
	cursor.execute("select keyword, target, count(*) as count from search where timestamp > %s and keyword!='' group by keyword,target order by count(*) desc limit 10",[int(time.time())-3600*24*7])
	hot = cursor.fetchall();

	return render_template('search/search_keyword.html', target=target, keyword=key, count=count, start=start, end=end, current=int(pageId), pages=pages, total=total, result=result, hot=hot)

# 根据分类返回创意
@app.route('/search/category')
def search_category():
	category = request.args.get('category')
	pageId = request.args.get('pageId')
	numPerPage = 10

	# 计算该分类的创意数量
	cursor.execute('select count(*) as count from idea where category=%s and locked=0',[category])
	count = cursor.fetchone()['count']

	# 获取该分类的创意并分页
	cursor.execute('select * from idea where category=%s and locked=0 order by praise desc, timestamp desc limit %s,%s',[category,int(pageId)*numPerPage,numPerPage])
	ideas = cursor.fetchall()

	# 转换时间戳
	for item in ideas:
		temp = int(time.time()) - int(item['timestamp'])
		if temp < 60:
			temp = str(temp) + 's'
		elif temp < 3600:
			temp = str(temp/60) + 'm'
		elif temp < 3600 * 24:
			temp = str(temp/3600) + 'h'
		else:
			temp = str(temp/(3600*24)) + 'd'
		item['timestamp'] = temp

	# 计算分页信息
	start = int(pageId) - 3
	end = int(pageId) + 3
	total = int(math.ceil(float(count) / numPerPage)) - 1
	if start < 0:
		start = 0
	if end > total:
		end = total
	pages = []
	for i in xrange(start, end + 1):
		pages.append(i)

	return render_template('search/search_category.html', category=category, count=count, start=start, end=end, current=int(pageId), pages=pages, total=total, ideas=ideas)

# 通知提醒
@app.route('/notice')
def notice():
	if session.get('username') == None:
		# 用户尚未登录
		return redirect(url_for('login'))
	else:
		# 获取和当前用户有关的动态
		username = session.get('username')
		cursor.execute("select * from activity where me=%s and checked=0 order by timestamp desc",[username])
		activities = cursor.fetchall()
		activityCount = len(activities)
		for item in activities:
			item['weekday'] = time.localtime(float(item['timestamp'])).tm_wday
			if item['weekday'] == 0:
				item['weekday'] = '星期一'
			elif item['weekday'] == 1:
				item['weekday'] = '星期二'
			elif item['weekday'] == 2:
				item['weekday'] = '星期三'
			elif item['weekday'] == 3:
				item['weekday'] = '星期四'
			elif item['weekday'] == 4:
				item['weekday'] = '星期五'
			elif item['weekday'] == 5:
				item['weekday'] = '星期六'
			elif item['weekday'] == 6:
				item['weekday'] = '星期日'
			item['timestamp'] = time.strftime('%m-%d', time.localtime(float(item['timestamp'])))
		cursor.execute("update activity set checked=1 where me=%s",[username])

		# 获取和当前用户有关的聊天信息
		cursor.execute("select source,sourceNickname,count(*) as count,content,timestamp from chat where target=%s and source!=%s and checked=0 group by source order by timestamp desc",[username,username])
		chats = cursor.fetchall()
		for item in chats:
			item['timestamp'] = time.strftime('%m-%d %H:%M', time.localtime(float(item['timestamp'])))
			cursor.execute("select portrait from user where username=%s",[item['source']])
			item['portrait'] = cursor.fetchone()['portrait']
		chatsCount = len(chats)

		return render_template('notice/notice.html',activities=activities,activityCount=activityCount,chats=chats,chatsCount=chatsCount)

# 私信界面
@app.route('/chat/<username>')
def chat(username):
	if session.get('username') == None:
		# 用户尚未登录
		return redirect(url_for('login'))
	else:
		# 用户已经登陆，获取所有聊天记录
		me = session.get('username')
		cursor.execute("select * from chat where (source=%s and target=%s) or (source=%s and target=%s) order by timestamp desc limit 100",[username,me,me,username])
		chats = cursor.fetchall()
		chats = sorted(chats, key=lambda x:(x['timestamp']))

		# 合并聊天时间戳
		currentTime = 0
		for item in chats:
			temp = float(item['timestamp'])
			if not currentTime == 0 and float(item['timestamp']) - currentTime < 600:
				item['timestamp'] = ''
			else:
				item['timestamp'] = (time.strftime('%m月%d日 %H:%M', time.localtime(float(item['timestamp'])))).lstrip('0')
			currentTime = temp

		# 将消息设置为已读
		cursor.execute('update chat set checked=1 where source=%s and target=%s',[username,me])

		# 获取用户头像和昵称
		cursor.execute("select portrait from user where username=%s",[me])
		myPortrait = cursor.fetchone()['portrait']
		cursor.execute("select nickname,portrait from user where username=%s",[username])
		portrait = cursor.fetchone()
		targetNickname = portrait['nickname']
		portrait = portrait['portrait']

		return render_template('notice/chat.html',target=username,targetNickname=targetNickname,chats=chats,myPortrait=myPortrait,portrait=portrait)

# 登陆
@app.route('/login', methods=['GET','POST'])
def login():
	error = None
	if request.method == 'GET':
		if not session.get('username') == None:
			return redirect(url_for('home'))
		else:
			return render_template('user/login.html', error=error)
	elif request.method == 'POST':
		username = request.form['username']
		password = request.form['password']
		if cursor.execute("select id from user where username=%s or email=%s", [username,username]) == 0:
			error = u"账号或邮箱不存在"
			return render_template('user/login.html', error=error)
		elif cursor.execute("select id from user where username=%s and password=%s", [username,unicode(md5(password).hexdigest().upper())]) + cursor.execute("select id from user where email=%s and password=%s", [username,unicode(md5(password).hexdigest().upper())]) == 0:
			error = u"账号或密码错误"
			return render_template('user/login.html', error=error)
		else:
			cursor.execute("update user set lastActive=%s, token=%s, TTL=100 where username=%s or email=%s",[str(int(time.time())),genKey(),username,username])
			cursor.execute("select username, token from user where username=%s or email=%s", [username,username])
			user = cursor.fetchone()
			session['username'] = user['username']
			session['token'] =  user['token']
			if not session.get('url') == None:
				url = session.get('url')
				session.pop('url', None)
				return redirect(url)
			else:
				return redirect(url_for('home'))

# 注销
@app.route('/logout')
def logout():
	if not session.get('username') == None:
		session.pop('username', None)
		return redirect(url_for('login'))
	else:
		return redirect(url_for('login')) 

# 注册
@app.route('/register', methods=['GET','POST'])
def register():
	if request.method == 'GET':
		if not session.get('username') == None:
			return redirect(url_for('/'))
		else:
			return render_template('user/register.html')
	elif request.method == 'POST':
		username = request.form['username']
		password = request.form['password']
		email = request.form['email']
		cursor.execute("insert into user(username,nickname,password,email) values(%s,%s,%s,%s)", [username,username,unicode(md5(password).hexdigest().upper()),email])
		return redirect(url_for('login'))

# if __name__ == '__main__':
# 	app.run()