###
# Copyright (c) 2017, cottongin
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import json

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Predictit')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x
    

class Predictit(callbacks.Plugin):
    """A plugin to fetch data from predictit.com API"""
    threaded = True
    
    def __init__(self, irc):
        self.__parent = super(Predictit, self)
        self.__parent.__init__(irc)
        self._google_api_key = self.registryValue('GoogleAPIKey')
        if len(self._google_api_key) <= 1:
            irc.reply("This plugin requires a Google API key to shorten URLs, please add yours via the configuration")
            return
        
    def die(self):
        self.__parent.die()

    ##
    # Internal Functions
    ##

    # spline
    def _httpget(self, url, h=None, d=None, l=False):
        """General HTTP resource fetcher. Pass headers via h, data via d, and to log via l."""

        try:
            if h and d:
                page = utils.web.getUrl(url, headers=h, data=d)
            else:
                h = {"User-Agent":"Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:17.0) Gecko/20100101 Firefox/17.0"}
                page = utils.web.getUrl(url, headers=h)
                try:
                    page = page.decode()
                except:
                    page = page.decode('iso-8859-1')
            return page
        except utils.web.Error as e:
            self.log.error("ERROR opening {0} message: {1}".format(url, e))
            return None

    # spline
    def _shortenUrl(self, url):
        """Shortens a long URL into a short one."""

        try:
            posturi = "https://www.googleapis.com/urlshortener/v1/url"
            #data = json.dumps({'longUrl' : url})
            data = json.dumps({"longUrl": "{0}".format(url)}) #.format(url)
            key = '?key={}'.format(self._google_api_key)
            request = self._httpget(posturi+key, h={'Content-Type':'application/json'}, d=data, l=False)
            return json.loads(request.decode())['id']
        except:
            return url


    def _parseDelta(self, last_trade_price, last_close_price):
        """parses delta and returns formatted string"""
        
        delta = round(last_trade_price - last_close_price, 2)
        
        if delta > 0:
            delta = '↑{}'.format(int(delta*100))
            delta = ircutils.mircColor(delta + '¢', 'green')
        elif delta < 0:
            delta = '↓{}'.format(int(delta*-100))
            delta = ircutils.mircColor(delta + '¢', 'red')
        else:
            delta = '---'
            
        return delta


    def _tradeString(self, last_trade_price):
        """parses last trade string and returns formatted string"""
        return 'Last Trade: ${:4.2f}'.format(last_trade_price)


    def _parseMarket(self, market):
        """parses market data and returns variables for formatting"""
        
        name = market['Name']
        last_price = market['LastTradePrice']
        last_trade_string = self._tradeString(last_price)
        close_price = (market['LastClosePrice']
            if market['LastClosePrice'] is not None
            else market['LastTradePrice'])
        delta = self._parseDelta(last_price, close_price)
        
        return name, last_trade_string, delta


    def _parseData(self, json_data, optmarket):
        """parses JSON data and returns strings"""
        
        reply_strings = []
        padding = 0
        
        for market in json_data['Contracts']:
            name = market['Name']
            padding = len(name) if len(name) > padding else padding
        
        print_url = self._shortenUrl(json_data['URL'])
        #truncate = False
        
        if len(json_data['Contracts']) > 1:
            # market has linked contracts
            name = ircutils.bold(json_data['Name'])
            reply_strings = ['{} | {}'.format(name, print_url)]
            #truncate = False
            if len(json_data['Contracts']) > 5:
                padding = 0
                truncate = 5
                for market in json_data['Contracts'][:truncate]:
                    name = market['Name']
                    padding = len(name) if len(name) > padding else padding
            else:
                truncate = len(json_data['Contracts'])
            for market in json_data['Contracts'][:truncate]:
                if len(optmarket.split('.')) == len(market['TickerSymbol'].split('.')):
                    if optmarket == market['TickerSymbol']:
                        print_url = self._shortenUrl(market['URL'])
                        name, last_trade_string, delta = self._parseMarket(market)
                        reply_strings.append('{} | {} ({})'.format(
                            name, last_trade_string, delta))
                else:
                    name, last_trade_string, delta = self._parseMarket(market)
                    reply_strings.append('{:{width}} | {} ({})'.format(
                        name, last_trade_string, delta, width=str(padding)))
        else:
            for market in json_data['Contracts']:
                name, last_trade_string, delta = self._parseMarket(market)
                reply_strings = ['{} | {} | {} ({})'.format(
                    ircutils.bold(name), print_url, last_trade_string, delta)]
                    
        return reply_strings


    def _fetchURL(self, url, h, optmarket):
        """fetches URL and returns JSON data"""
        
        try:
            data = utils.web.getUrl(url.format(optmarket), headers=h)
            data = data.decode()
            json_data = json.loads(data)
        except:
            irc.reply('No results found for "{}"'.format(optmarket))
            return
        return json_data


    def _reply(self, irc, reply_strings, optmarket):
        """replies for items in reply_strings"""
        if not reply_strings:
            irc.reply('No results found for "{}"'.format(optmarket))
            return
        else:
            for item in reply_strings:
                irc.reply(item)

    ##
    # Public functions
    ##
        
    @wrap(['somethingwithoutspaces'])
    def predictit(self, irc, msg, args, optmarket):
        """<predictit ticker symbol>
        Returns basic info on <predictit ticker symbol>
        """
        
        optmarket = optmarket.upper()
        
        # API link and header to retreive it in JSON format
        url = 'https://www.predictit.org/api/marketdata/ticker/{}'
        h = {'Accept': 'application/json'}
        
        # grab the data
        json_data = self._fetchURL(url, h, optmarket)
        
        if not json_data:
            irc.reply('No results found for "{}"'.format(optmarket))
            return
        
        # parse the data
        reply_strings = self._parseData(json_data, optmarket)
        
        # reply/output
        self._reply(irc, reply_strings, optmarket)


Class = Predictit


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
