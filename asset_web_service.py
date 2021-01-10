from flask import Flask, abort, escape, request, jsonify
import requests
import lxml.html


DAILY_PAGE_SNAPSHOT = 'cbr_currency_base_daily.html'
INDICATORSs_PAGE_SNAPSHOT = 'cbr_key_indicators.html'
DAILY_URL = 'https://www.cbr.ru/eng/currency_base/daily/'
INDICATORS_URL = 'https://www.cbr.ru/eng/key-indicators/'
app = Flask(__name__)


class Asset:
    """class to store asset and calculate its revenue"""
    def __init__(self, name: str, char_code: str, capital: float, interest: float):
        self.char_code = char_code
        self.name = name
        self.capital = capital
        self.interest = interest

    def calculate_revenue(self, years: int, rate: float) -> float:
        """calc revenue for one asset for given period"""
        revenue = rate * self.capital * ((1.0 + self.interest) ** years - 1.0)
        return revenue

    @classmethod
    def build_from_query(cls, char_code, name, capital, interest):
        """build asset from url"""
        char_code = escape(char_code)
        name = escape(name)
        capital = float(capital)
        interest = float(interest)
        asset = cls(char_code=char_code, name=name, capital=capital, interest=interest)
        return asset

    def get_asset(self) -> list:
        """get asset chars"""
        return [self.char_code, self.name, self.capital, self.interest]


def parse_cbr_currency_base_daily(html_string: str) -> dict:
    """parses HTML from base daily page into sorted dict of currency rates"""
    currencies = {}
    elements = lxml.html.fromstring(html_string).xpath('//table[@class="data"]/tbody/tr')
    for el in elements[1:]:
        char_code = el.text_content().split('\n')[2].strip()
        unit = int(el.text_content().split('\n')[3])
        rate = float(el.text_content().split('\n')[5])
        currencies[char_code] = round(rate / unit, 8)
    return currencies


def parse_cbr_key_indicators(html_string: str) -> dict:
    """parses HTML from key indicators page into sorted dict of currency rates"""
    elements = lxml.html.fromstring(html_string).xpath('//div[@class="table key-indicator_table"]')
    # get precious metals
    metals = elements[1].text_content().split('\n')[11:-4]
    indicators = dict(zip(
        [code.strip() for code in metals[::9]],  # char codes
        [float(price.replace(',', '')) for price in metals[3::9]]  # prices
    ))
    # get USD/EUR
    indicators['USD'] = float(elements[0].text_content().split('\n')[16])
    indicators['EUR'] = float(elements[0].text_content().split('\n')[-5])
    return indicators


@app.errorhandler(404)
def page_do_not_exist(error):
    """404 handler"""
    return "This route is not found", 404


@app.errorhandler(503)
def cbr_is_unavailable(error):
    """503 handler"""
    return "CBR service is unavailable", 503


@app.route("/cbr/daily")
def get_daily_currencies():
    """safely get values from daily CBR page"""
    try:
        response = requests.get(DAILY_URL)
        if response.status_code == 200:
            return parse_cbr_currency_base_daily(response.text)
        abort(503)
    except:
        abort(503)


@app.route("/cbr/key_indicators")
def get_indicators():
    """safely get values from indicators CBR page"""
    try:
        response = requests.get(INDICATORS_URL)
        if response.status_code == 200:
            return parse_cbr_key_indicators(response.text)
        abort(503)
    except:
        abort(503)


@app.route("/api/asset/add/<char_code>/<name>/<float:capital>/<float:interest>")
@app.route("/api/asset/add/<char_code>/<name>/<float:capital>/<int:interest>")
@app.route("/api/asset/add/<char_code>/<name>/<int:capital>/<float:interest>")
@app.route("/api/asset/add/<char_code>/<name>/<int:capital>/<int:interest>")
def add_asset(char_code, name, capital, interest):
    """add new asset via URL params"""
    new_asset = Asset.build_from_query(char_code, name, capital, interest)
    if asset_has_duplicate_name(new_asset):
        return "Duplicate asset name", 403
    all_assets.append(new_asset)
    return f"Asset {new_asset.name} was successfully added"


def asset_has_duplicate_name(new_asset: Asset) -> bool:
    """check if asset already exists"""
    for asset in all_assets:
        if asset.name == new_asset.name:
            return True
    return False


@app.route("/api/asset/list")
def print_assets():
    """print all available assets"""
    res = []
    all_assets.sort(key=lambda x: x.char_code)
    for asset in all_assets:
        res.append(asset.get_asset())
    return jsonify(res)


@app.route("/api/asset/cleanup")
def clean_assets():
    """remove all assets"""
    global all_assets
    all_assets = []
    return '', 200


@app.route("/api/asset/get")
def get_assets_by_name():
    """get asset one-by-one by URL query"""
    input_names = request.args.getlist("name")
    res = []
    all_assets.sort(key=lambda x: x.char_code)
    for asset in all_assets:
        if asset.name in input_names:
            res.append(asset.get_asset())
    return jsonify(res)


@app.route("/api/asset/calculate_revenue")
def calc_all_revenue():
    """calculate revenue for all assets"""
    try:
        input_periods = request.args.getlist("period")
        indicators = get_indicators()
        currencies = get_daily_currencies()
        res = {}
        for period in input_periods:
            res[period] = 0
            for asset in all_assets:
                asset_code = str(asset.char_code)
                # case if we have asset in roubles
                if asset_code == 'RUB':
                    currencies['RUB'] = 1
                if asset_code in indicators:
                    rate = indicators[asset_code]
                else:
                    rate = currencies.get(asset_code, 0)
                res[period] += asset.calculate_revenue(int(period), rate)
            res[period] = round(res[period], 8)
        return res
    except:
        abort(503)


all_assets = []
