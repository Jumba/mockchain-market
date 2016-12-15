import os
import sys

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from market.database.backends import MemoryBackend
from market.database.database import MockDatabase
from market.views import main_view
from marketGUI.market_app import MarketApplication
from market.api.api import MarketAPI
from navigation import NavigateUser
from login_controller import LoginController
from profile_controller import ProfileController
from borrowers_portfolio_controller import BorrowersPortfolioController
from openmarket_controller import OpenMarketController
from place_loan_request_controller import PlaceLoanRequestController

class MainWindowController(QMainWindow, main_view.Ui_MainWindow):
    def __init__(self, parent=None, app=None):
        super(MainWindowController, self).__init__(parent)
        # self.database = MockDatabase(MemoryBackend())
        # self.api = MarketAPI(self.database)
        self.mainwindow = self #to make moving to another class easier
        self.app = app
        self.api = app.api
        self.setupUi(self)
        self.navigation = NavigateUser(self)
        self.bplr_payload = {}
        # self.set_navigation()
        # self.bplr_submit_button.clicked.connect(self.bplr_submit_loan_request)
        # self.fiplr1_loan_requests_table.doubleClicked.connect(self.fiplr2_view_loan_request)
        # self.openmarket_open_market_table.doubleClicked.connect(self.openmarket_view_campaign)
        # self.fiplr1_view_loan_request_pushbutton.clicked.connect(self.fiplr2_view_loan_request)
        # self.fiplr2_accept_pushbutton.clicked.connect(self.fiplr2_accept_loan_request)
        # self.fiplr2_reject_pushbutton.clicked.connect(self.fiplr2_reject_loan_request)
        # self.icb_place_bid_pushbutton.clicked.connect(self.icb_place_bid)
        self.setupObjects()
        self.stackedWidget.setCurrentIndex(0)
        self.login_controller = LoginController(self)
        self.profile_controller = ProfileController(self)
        self.bp_controller = BorrowersPortfolioController(self)
        self.openmarket_controller = OpenMarketController(self)
        self.bplr_controller = PlaceLoanRequestController(self)

    def fiplr1_load_all_pending_loan_requests(self):
        print 'Loading second screen!'
        # TODO request the contents with the uuid that is being returned from the following:
        # pop = self.api.load_all_loan_requests(self.user_bank)
        # print pop
        self.fiplr1_populate_table([self.bplr_payload])
        self.next_screen()


    # method for populating the pending resquest table.
    def fiplr1_populate_table(self, payload):
        self.fiplr1_loan_requests_table.setRowCount(len(payload))
        for i in range(0, len(payload)):
            row = payload[i]
            self.fiplr1_loan_requests_table.item(i, 0).setText('Bouwerslaan ' + row['house_number']+' , '+row['postal_code'])
            self.fiplr1_loan_requests_table.item(i, 1).setText(str(row['mortgage_type']))
            self.fiplr1_loan_requests_table.item(i, 2).setText(str(row['amount_wanted']))
            self.fiplr1_loan_requests_table.item(i, 3).setText(str(row['price']))

    def fiplr2_view_loan_request(self):
        content = [self.bplr_payload]
        chosen_index = self.fiplr1_loan_requests_table.selectedIndexes()[0].row()
        chosen_request = content[chosen_index]     # index of the row
        print 'content'
        print content
        #personal information
        self.fiplr2_firstname_lineedit.setText(str(self.borrower_profile_payload['first_name']))
        self.fiplr2_lastname_lineedit.setText(str(self.borrower_profile_payload['last_name']))
        self.fiplr2_address_lineedit.setText(str('Laanlaan ' + self.borrower_profile_payload['current_housenumber'] + ' ' + self.borrower_profile_payload['current_postalcode']))
        self.fiplr2_phonenumber_lineedit.setText(str(self.borrower_profile_payload['phonenumber']))
        self.fiplr2_email_lineedit.setText(str(self.borrower_profile_payload['email']))

        #information about the request
        self.fiplr2_property_address_lineedit.setText('Bouwerslaan '+chosen_request['house_number']+' , '+chosen_request['postal_code'])
        # TODO rename the fiplr2_loan_amount_lineedit
        self.fiplr2_loan_amount_lineedit.setText(str(chosen_request['amount_wanted']))
        self.fiplr2_mortgage_type_lineedit.setText(str(chosen_request['mortgage_type']))
        self.fiplr2_property_value_lineedit.setText(str(chosen_request['price']))
        self.fiplr2_description_textedit.setText(str(chosen_request['description']))
        self.next_screen()

    def fiplr2_accept_loan_request(self):
        # TODO api does not accept payload set by the bank in the fiplr2 screen
        bank_offer = {
            'amount': self.fiplr2_offer_amount_lineedit.text(),
            'interest_rate': self.fiplr2_offer_interest_lineedit.text(),
            'default_rate': self.fiplr2_default_rate_lineedit.text(),
            'duration': self.fiplr2_loan_duration_lineedit.text()
            # 'mortgage_id': self.fiplr2_loan_duration_lineedit.text()
        }
        self.openmarket_view_open_market(bank_offer)
        # TODO send the payload to the api
        # self.api.accept_loan_request()

    def fiplr2_reject_loan_request(self):
        self.previous_screen()
        # TODO do an actual reject with the api



#################################################bs#####################################################################

    # def set_navigation(self):
    #     self.next_1.clicked.connect(self.next_screen)
    #     self.next_2.clicked.connect(self.next_screen)
    #     self.next_3.clicked.connect(self.next_screen)
    #     self.next_4.clicked.connect(self.next_screen)
    #     self.next_5.clicked.connect(self.next_screen)
    #     self.next_6.clicked.connect(self.next_screen)
    #     self.next_7.clicked.connect(self.next_screen)
    #     self.next_8.clicked.connect(self.next_screen)
    #     self.prev_1.clicked.connect(self.previous_screen)
    #     self.prev_2.clicked.connect(self.previous_screen)
    #     self.prev_3.clicked.connect(self.previous_screen)
    #     self.prev_4.clicked.connect(self.previous_screen)
    #     self.prev_5.clicked.connect(self.previous_screen)
    #     self.prev_6.clicked.connect(self.previous_screen)
    #     self.prev_7.clicked.connect(self.previous_screen)
    #     self.prev_8.clicked.connect(self.previous_screen)
    #
    # def next_screen(self):
    #     self.stackedWidget.setCurrentIndex((self.stackedWidget.currentIndex() + 1) % self.stackedWidget.count())
    #
    # def previous_screen(self):
    #     self.stackedWidget.setCurrentIndex((self.stackedWidget.currentIndex() - 1) % self.stackedWidget.count())


    def setupObjects(self):
        #create user
        # self.user_borrower,pub_key1,priv_key1 = self.api.create_user()
        # self.user_investor,pub_key2,priv_key2 = self.api.create_user()
        # self.user_bank,pub_key3,priv_key3 = self.api.create_user()


        #create profile for users
        self.borrower_profile_payload = {'role': 1, 'first_name': 'Bob', 'last_name': 'Bouwer, de', 'email': 'bob@gmail.com',
                    'iban': 'NL53 INGBB 04027 30393', 'phonenumber': '+31632549865',
                    'current_postalcode': '1234 CD', 'current_housenumber': '24', 'documents_list': []}
        investor_payload = {'role': 2, 'first_name': 'Ruby', 'last_name': 'Cue', 'email': 'example1@example.com', 'iban': 'NL53 INGB 04097 30394', 'phonenumber': '+3170253719290'}
        bank_payload = {'role': 3}



        # print self.api.create_profile(self.user_borrower, self.borrower_profile_payload)
        # print self.api.create_profile(self.user_investor, investor_payload)
        # print self.api.create_profile(self.user_bank, bank_payload)
