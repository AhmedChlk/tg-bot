from appium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def init_appium(server_url: str = "http://localhost:4723/wd/hub"):
    """Initialise la connexion Appium avec un émulateur Android."""
    desired_caps = {
        "platformName": "Android",
        "deviceName": "OnePlus9",
        "platformVersion": "11",
        "automationName": "UiAutomator2",
        "appPackage": "com.example.app",
        "appActivity": ".MainActivity",
    }
    driver = webdriver.Remote(server_url, desired_caps)
    driver.implicitly_wait(10)
    return driver
