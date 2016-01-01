#!/usr/bin/env python


from __future__ import print_function

# Core
import collections
from functools import wraps
import logging
import pprint
import random
import time
import ConfigParser

# Third-Party
import argh

from clint.textui import progress
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import \
    TimeoutException, UnexpectedAlertPresentException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import selenium.webdriver.support.expected_conditions as ec
import selenium.webdriver.support.ui as ui
from splinter import Browser
from splinter.exceptions import ElementDoesNotExist


# Local

logging.basicConfig(
    format='%(lineno)s - %(message)s',
    level=logging.INFO
)

random.seed()

pp = pprint.PrettyPrinter(indent=4)

base_url = 'http://www.trafficmonsoon.com/'

action_path = dict(
    login='login',
    view_ads='member/surf.php',
    dashboard='member/overview.php',
    withdraw='DotwithdrawForm.asp',
    buy_pack='member/optools_ppc.php'
)

one_minute = 60
three_minutes = 3 * one_minute
ten_minutes = 10 * one_minute
one_hour = 3600


def url_for_action(action):
    return "{0}/{1}".format(base_url, action_path[action])


def loop_forever():
    while True:
        pass


def clear_input_box(box):
    box.type(Keys.CONTROL + "e")
    for i in xrange(100):
        box.type(Keys.BACKSPACE)
    return box


# http://stackoverflow.com/questions/16807258/selenium-click-at-certain-position
def click_element_with_offset(driver, elem, x, y):
    action = ActionChains(driver)
    echo_print("Moving to x position", x)
    echo_print("Moving to y position", y)
    action.move_to_element_with_offset(elem, x, y)
    print("OK now see where the mouse is...")
    action.click()
    action.perform()


def page_source(browser):
    document_root = browser.driver.page_source
    return document_root


def wait_visible(driver, locator, by=By.XPATH, timeout=30):
    """

    :param driver:
    :param locator:
    :param by:
    :param timeout:
    :return:
    """
    try:
        ui.WebDriverWait(driver, timeout).until(ec.visibility_of_element_located((by, locator)))
        logging.info("wait_visible succeeded.")
        return driver.find_element(by, locator)
    except TimeoutException:
        logging.info("wait_visible TimeoutException.")
        return False


def wait_element_selected(driver, locator, by=By.XPATH, timeout=30):
    """

    :param driver:
    :param locator:
    :param by:
    :param timeout:
    :return:
    """
    try:
        if ui.WebDriverWait(driver, timeout).until(ec.element_located_to_be_selected((by, locator))):
            return driver.find_element(by, locator)
    except TimeoutException:
        return False


def maybe_accept_alert(driver):
    try:
        logging.warn("Probing for alert.")
        ui.WebDriverWait(driver, 3).until(ec.alert_is_present(),
                                          'Timed out waiting for PA creation ' +
                                          'confirmation popup to appear.')
        print("Switching to alert.")
        alert = driver.switch_to_alert()
        alert.accept()
        print("alert accepted")
    except TimeoutException:
        print("no alert")


def trap_unexpected_alert(func):
    @wraps(func)
    def wrapper(self):
        try:
            return func(self)
        except UnexpectedAlertPresentException:
            print("Caught unexpected alert.")
            return 254
        except WebDriverException:
            print("Caught webdriver exception.")
            return 254

    return wrapper


def trap_alert(func):
    @wraps(func)
    def wrapper(self):
        try:
            return func(self)
        except UnexpectedAlertPresentException:
            logging.info("Caught UnexpectedAlertPresentException.")
            alert = self.browser.driver.switch_to_alert()
            alert.accept()
            return 254
        except WebDriverException:
            logging.info("Caught webdriver exception.")
            return 253

    return wrapper


def get_element_html(driver, elem):
    return driver.execute_script("return arguments[0].innerHTML;", elem)


def echo_print(text, elem):
    print("{0}={1}.".format(text, elem))


control_a = "\x01"


class Entry(object):
    def __init__(self, username, password, browser):
        self._username = username
        self._password = password
        self.browser = browser
        self.account_balance = None

    def enter_user_pass(self):
        self.browser.find_by_name('Username').type(control_a + self._username)
        self.browser.find_by_name('Password').type("{0}\t".format(self._password))

    def enter_captcha(self):
        captcha_answer = raw_input("CAPTCHA characters: ")
        self.browser.find_by_name('turing').type("{0}\n".format(captcha_answer))

    def maybe_robot_login(self):
        logging.info("Waiting on 'You are a robot...'")
        if wait_visible(self.browser.driver, "//div[@class='alert alert-danger']", timeout=5):
            self.enter_user_pass()
            self.enter_captcha()

    def wait_on_login_ad(self):
        logging.info("Waiting on login ad to complete...")
        if wait_visible(self.browser.driver, '//span[text()="Back to Dashboard"]', timeout=60):
            logging.info("back to dashboard seen.")
        else:
            self.login()

    def login(self):
        print("Logging in...")

        self.browser_visit('login')

        self.enter_user_pass()
        self.enter_captcha()
        self.maybe_robot_login()
        self.wait_on_login_ad()

    def browser_visit(self, action_label):
        try:
            print("Visiting URL for {0}".format(action_label))
            self.browser.visit(url_for_action(action_label))
            maybe_accept_alert(self.browser.driver)
            return 0
        except TimeoutException:
            logging.info("Page load timeout.")
            pass
        except UnexpectedAlertPresentException:
            print("Caught UnexpectedAlertPresentException.")
            logging.warn("Attempting to dismiss alert")
            alert = self.browser.driver.switch_to_alert()
            alert.dismiss()
            return 254
        except WebDriverException:
            print("Caught webdriver exception.")
            return 253

    def view_ads(self, surf_amount):

        for i in xrange(1, surf_amount + 1):
            while True:
                self.browser_visit('view_ads')
                print("Viewing ad {0} of {1}".format(i, surf_amount))
                result = self.view_ad()
                if result == 0:
                    break
        self.browser_visit('dashboard')

    @trap_alert
    def view_ad(self):
        wait_visible(
            self.browser.driver, "//p[text()='Click identical image to validate site view.']", timeout=60
        )
        candidate_images_elem = self.browser.find_by_xpath('//div[@id="site_loader"]/img')
        image_count = collections.defaultdict(lambda: 0)
        for image in candidate_images_elem:
            image_count[image['src']] += 1
            if image_count[image['src']] > 1:
                logging.info("Clicking image.")
                image.click()
                return 0
        return 255

    @staticmethod
    def wait_on_ad():
        time_to_wait_on_ad = random.randrange(40, 50)
        for _ in progress.bar(range(time_to_wait_on_ad)):
            time.sleep(1)

    def buy_pack(self):
        self.browser_visit('buy_pack')
        self.browser.click_link_by_partial_text("Buy AdPack")

        button = wait_visible(self.browser.driver, '//button[@data-toggle="dropdown"]')
        button.click()

        try:
            logging.info("")
            self.browser.find_by_xpath('//span[contains(text(), "account balance")]').first.click()
            time.sleep(5)
        except ElementDoesNotExist:
            logging.info("Account balance element does not exist.")
            return 255

        logging.info("Clicking preview.")
        self.browser.find_by_xpath('//input[@type="submit"]').first.click()  # preview button
        time.sleep(5)

        logging.info("Clicking confirm.")
        self.browser.find_by_xpath('//input[@type="submit"]')[1].click()  # confirm
        time.sleep(5)

        logging.info("Accepting alert if present...")
        maybe_accept_alert(self.browser.driver)

    def calc_account_balance(self):
        time.sleep(1)

        logging.warn("visiting dashboard")
        self.browser_visit('dashboard')

        logging.warn("finding element by xpath")
        elem = self.browser.find_by_xpath(
            '/html/body/table[2]/tbody/tr/td[2]/table/tbody/tr/td[2]/table[6]/tbody/tr/td/table/tbody/tr[2]/td/h2[2]/font/font'
        )

        print("Elem Text: {}".format(elem.text))

        self.account_balance = float(elem.text[1:])

        print("Available Account Balance: {}".format(self.account_balance))

    def calc_credit_packs(self):
        time.sleep(1)

        logging.warn("visiting dashboard")
        self.browser_visit('dashboard')

        logging.warn("finding element by xpath")
        elem = self.browser.find_by_xpath(
            "//font[@color='#009900']"
        )

        print("Active credit packs = {0}".format(elem[0].text))
        # for i, e in enumerate(elem):
        #     print("{0}, {1}".format(i, e.text))


def main(conf, surf=False, buy_pack=False, stay_up=False, surf_amount=12):
    config = ConfigParser.ConfigParser()
    config.read(conf)
    username = config.get('login', 'username')
    password = config.get('login', 'password')

    with Browser('chrome') as browser:

        browser.driver.set_window_size(1200, 1100)
        browser.driver.set_window_position(200, 0)
        browser.driver.set_page_load_timeout(180)

        e = Entry(username, password, browser)

        e.login()

        if buy_pack:
            e.buy_pack()

        if surf:
            e.view_ads(surf_amount)

        if stay_up:
            loop_forever()


if __name__ == '__main__':
    argh.dispatch_command(main)
