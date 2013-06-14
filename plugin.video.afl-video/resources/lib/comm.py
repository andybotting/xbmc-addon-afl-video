#
#	 AFL Video XBMC Plugin
#	 Copyright (C) 2012 Andy Botting
#
#	 AFL Video is free software: you can redistribute it and/or modify
#	 it under the terms of the GNU General Public License as published by
#	 the Free Software Foundation, either version 3 of the License, or
#	 (at your option) any later version.
#
#	 AFL Video is distributed in the hope that it will be useful,
#	 but WITHOUT ANY WARRANTY; without even the implied warranty of
#	 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	 GNU General Public License for more details.
#
#	 You should have received a copy of the GNU General Public License
#	 along with AFL Video.  If not, see <http://www.gnu.org/licenses/>.
#

import urllib, urllib2
import config
import classes
import utils
import datetime
import time

# AMF services
from pyamf.remoting.client import RemotingService

# Use local etree to get v1.3.0
import etree.ElementTree as ET

# Parsing SMIL data
from BeautifulSoup import BeautifulStoneSoup

try:
	import simplejson as json
except ImportError:
	import json

try:
	import xbmc, xbmcgui, xbmcplugin, xbmcaddon
except ImportError:
	pass # for PC debugging

def fetch_url(url, token=None):
	"""
		Simple function that fetches a URL using urllib2.
		An exception is raised if an error (e.g. 404) occurs.
	"""
	utils.log("Fetching URL: %s" % url)

	# Token headers
	headers = {}
	if token:
		headers = {'x-media-mis-token': token}

	request = urllib2.Request(url, headers=headers)
	return urllib2.urlopen(request).read()


def fetch_token():
	"""
		This functions performs a HTTP POST to the token URL
		and it will return a token required for API calls
	"""	
	req = urllib2.Request(config.TOKEN_URL, '')
	res = urllib2.urlopen(req)
	json_result = json.loads(res.read())
	res.close()
		
	return json_result['token']


def parse_amf_video(video_item):
	"""
		Parse the AMF video item and construct a video object from it.
	"""
	v = video_item['content']
	new_video = classes.Video()
	new_video.id = v['contentId']
	new_video.title = v['title']
	new_video.description = v['description']

	# Convert h:m:s to seconds
	if v.has_key('duration') and v['duration'] is not None:
		h, m, s = [int(i) for i in v['duration'].split(':')]
		new_video.duration = 3600*h + 60*m + s

	# Replace to higher res thumbnails
	if v['imageUrl']:
		new_video.thumbnail = v['imageUrl'].replace('89x50.jpg', '326x184.jpg')

	return new_video


def parse_json_video(video_data):
	"""
		Parse the JSON data and construct a video object from it.
	"""
	new_video = classes.Video()
	new_video.title = video_data['title']
	new_video.description = video_data['description']
	new_video.thumbnail = video_data['media$thumbnails'][0]['plfile$url']
	return new_video


def parse_json_video_new(video_data):
	"""
		Parse the JSON data and construct a video object from it for a list
		of videos
	"""
	# Find our quality setting and fetch the URL
	__addon__ = xbmcaddon.Addon()
	qual = __addon__.getSetting('QUALITY')

	video = classes.Video()
	video.title = video_data['title']
	video.description = video_data['description']
	video.thumbnail = video_data['thumbnailPath']
	timestamp = time.mktime(time.strptime(video_data['customPublishDate'], '%Y-%m-%dT%H:%M:%S.%f+0000'))
	video.date = datetime.date.fromtimestamp(timestamp)

	video_format = None
	for v in video_data['mediaFormats']:
		if int(v['bitRate']) == config.VIDEO_QUALITY[qual]:
			video_format = v
			break

	video.url = video_format['sourceUrl']
	video.duration = video_format['duration']

	return video

def get_videos(channel_id):
	"""
		Get the list of videos from the AMF service.
	"""
	videos = []
	client = RemotingService('http://afl.bigpondvideo.com/App/AmfPhp/gateway.php')
	service = client.getService('Miscellaneous')
	params = {
		'navId': channel_id,
		'startRecord': '0',
		'howMany': '50',
		'platformId': '1',
		'phpFunction': 'getClipList',
		'asFunction': 'publishClipList'
	}

	videos_list = service.getClipList(params)

	for video_item in videos_list[0]['items']:
		video = parse_amf_video(video_item)
		videos.append(video)
	return videos


def get_url_from_smil(data):

	"""
	<smil xmlns="http://www.w3.org/2005/SMIL21/Language">
		<head></head>
		<body>
			<seq>
				<video src="http://bponlinewoc2264.ngcdn.telstra.com/PlatformRelease/487/684/GEEL_PRESSER.mp4" [other stuff]></video>
			</seq>
		</body>
	</smil>
	"""
	soup = BeautifulStoneSoup(data)
	src = soup.find('video')['src']
	return src


def get_video(video_id):
	
	url = "http://feed.theplatform.com/f/gqvPBC/AFLProd_Online_H264?byGuid=%s&form=json" % video_id
	data = fetch_url(url)

	json_data = json.loads(data)

	if len(json_data['entries']) == 0:
		raise IOError('Video URL not found')

	# Only one entry with this function
	video_data = json_data['entries'][0]
	video = parse_json_video(video_data)

	# Find our quality setting and fetch the URL
	__addon__ = xbmcaddon.Addon()
	qual = __addon__.getSetting('QUALITY')

	# Set the last video entry (usually highest qual) as a default fallback
	# in case we don't make a match below
	playlist = video_data['media$content'][0]['plfile$url']

	for video_entry in video_data['media$content']:
		# Match the video for the quality in the addon settings
		# The value should look like 1024000, but we only store 1024 in config
		if video_entry['plfile$bitrate'] == config.VIDEO_QUALITY[qual] * 1000:
			playlist = video_entry['plfile$url']

	smil = fetch_url(playlist)

	# Set the URL
	video.url = get_url_from_smil(smil)

	return video


def get_videos_new(category):
	"""
		New function for listing videos, not yet in use
	"""
	video_list = []

	# Get a token. TODO: Cache this
	token = fetch_token()

	# Category names are URL encoded
	category_encoded = urllib.quote(category)
	url = config.VIDEO_LIST_URL + '?categories=' + category_encoded

	data = fetch_url(url, token=token)
	json_data = json.loads(data)
	video_assets = json_data['videos'][0]['videos']

	for video_asset in video_assets:
		video = parse_json_video_new(video_asset)
		video_list.append(video)

	return video_list	


def get_round(round_id):
	"""
		Fetch the round and return the results
	"""
	round_matches = []
	round_url = config.ROUND_URL

	# Pass a 'latest' string in round_id to get 'this week'
	if round_id != 'latest':
		round_url = "%s/%s" % (round_url, round_id)

	xml = fetch_url(round_url)
	rnd = ET.fromstring(xml)

	matches = rnd.find('matches').getchildren()

	for m in matches:
		d = dict(m.items())

		if d['homeSquadId']:
			match = {}
			home_team = utils.get_team(d['homeSquadId'])['name']
			away_team = utils.get_team(d['awaySquadId'])['name']
			match['name'] = "%s v %s" % (home_team, away_team)
			match['id'] = d['FixtureId']
			match['round_id'] = dict(rnd.items())['id']
			# Add date/time
			round_matches.append(match)

	return round_matches

	
def get_match_video(round_id, match_id, quality):

	match_video = []
	round_url = "%s/%s" % (config.ROUND_URL, round_id)

	try:
		xml = fetch_url(round_url)
		rnd = ET.fromstring(xml)

		matches = rnd.find('matches')
		match = matches.find('match[@FixtureId="%s"]' % match_id)

		qualities = match.find('qualities')
		quality = qualities.find('quality[@name="%s"]' % config.REPLAY_QUALITY[quality])
		periods = quality.find('periods')
	
		for qtr in periods.getchildren():
			qtr_dict = dict(qtr.items())
			match_video.append(qtr_dict)
	except:
		return None

	return match_video

