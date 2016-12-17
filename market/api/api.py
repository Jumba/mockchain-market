import time
from datetime import timedelta, datetime
from enum import Enum
from twisted.internet.task import LoopingCall

from market.api.crypto import generate_key, get_public_key
from market.community.community import MortgageMarketCommunity
from market.community.queue import MessageQueue
from market.database.database import Database
from market.dispersy.crypto import ECCrypto
from market.models.house import House
from market.models.loans import LoanRequest, Mortgage, Investment, Campaign
from market.models.profiles import BorrowersProfile
from market.models.profiles import Profile
from market.models.role import Role
from market.models.user import User


class STATUS(Enum):
    NONE = 0
    PENDING = 1
    ACCEPTED = 2
    REJECTED = 3


CAMPAIGN_LENGTH_DAYS = 30


class MarketAPI(object):
    """
    Create a MarketAPI object.

    The constructor requires one variable, the `Database` used for storage.
    """
    def __init__(self, database):
        assert isinstance(database, Database)
        self._database = database
        self._user_key = None
        self.crypto = ECCrypto()
        self.community = MortgageMarketCommunity
        self.user_candidate = {}
        self.queue = MessageQueue()


    @property
    def db(self):
        return self._database

    def user_key(self):
        return self._user_key

    def _get_user(self, user):
        if isinstance(user, User):
            return self.db.get(User._type, user.id)
        elif isinstance(user, str):
            return self.db.get(User._type, user)
        else:
            return None

    def create_user(self):
        """
           Create a dispersy user by generating a key public/private pair.

           Returns None if the user creation process fails.


           :return: A tuple with the User object, the public key and the private key. The keys encoded in HEX.
           :rtype: (:any:`User`, Public, Private) or None
        """
        key = self.crypto.generate_key(u'high')
        public_bin = self.crypto.key_to_bin(key.pub())
        private_bin = self.crypto.key_to_bin(key)

        user = User(public_key=public_bin.encode("HEX"), time_added=time.time())  # Save the public key bin (encode as HEX) in the database along with the register time.
        self.db.backend.set_option('user_key_pub', public_bin.encode("HEX"))
        self.db.backend.set_option('user_key_priv', private_bin.encode("HEX"))

        if self.db.post(User._type, user):
            return user, public_bin.encode("HEX"), private_bin.encode("HEX")
        else:
            return None

    def login_user(self, private_key):
        """
            Login a user by generating the public key from the private key supplied, and searching the user object in the database using the generated key.

        :param private_key: The private key of the user encoded in HEX.
        :type private_key: str
        :return: The logged in User if successful, None otherwise.
        """
        private_key = private_key.decode("HEX")
        if get_public_key(private_key):
            user = self.db.get(User._type, get_public_key(private_key))
            return user
        return None

    def create_profile(self, user, payload):
        """
        Creates a new profile and saves it to the database. The profile can either be a normal Profile or a BorrowersProfile, depending on the role given in the payload.
        Overwrites the old profile. The role 'FINANCIAL_INSTITUTION' can not have a profile, but the role will be set. Thus the function will return `True`.

        The payload contains the following data. If the role is `1` for `BORROWER` then the last three fields must also be pushed.

        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | Key                  | Description                                                                                        | Required for Profile (if role is not borrower) |
        +======================+====================================================================================================+================================================+
        | role                 | The role id uit of the following tuple: ('NONE', 'BORROWER', 'INVESTOR', 'FINANCIAL_INSTITUTION')  | Yes                                            |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | first_name           | The user's first name                                                                              | Yes                                            |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | last_name            | The user's last name                                                                               | Yes                                            |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | email                | The user's email address                                                                           | Yes                                            |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | iban                 | The user's IBAN                                                                                    | Yes                                            |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | phonenumber          | The user's phone number                                                                            | Yes                                            |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | current_postalcode   | The user's current postal code                                                                     | No                                             |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | current_housenumber  | The user's current house number                                                                    | No                                             |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+
        | documents_list       | A list of documents                                                                                | No                                             |
        +----------------------+----------------------------------------------------------------------------------------------------+------------------------------------------------+

        :param user: The user for whom a profile has to be made
        :type user: :any:`User`
        :param payload: The payload containing the data for the profile, as described above.
        :type payload: dict
        :return The Profile or True if a bank role was set or False if the payload is malformed
        :rtype :any:`Profile` or True or False
        """
        assert isinstance(user, User)
        assert isinstance(payload, dict)

        try:
            role = Role(payload['role'])
            user.role_id = role.value

            profile = None
            if role.name == 'INVESTOR':
                profile = Profile(payload['first_name'], payload['last_name'], payload['email'], payload['iban'], payload['phonenumber'])
                user.profile_id = self.db.post(Profile._type, profile)
            elif role.name == 'BORROWER':
                profile = BorrowersProfile(payload['first_name'], payload['last_name'], payload['email'], payload['iban'],
                                           payload['phonenumber'], payload['current_postalcode'], payload['current_housenumber'], payload['documents_list'])
                user.profile_id = self.db.post(BorrowersProfile._type, profile)
            elif role.name == 'FINANCIAL_INSTITUTION':
                self.db.put(User._type, user.id, user)
                return True

            self.db.put(User._type, user.id, user)
            return profile
        except KeyError:
            return False

    def load_profile(self, user):
        """
        Load the given users profile.

        Depending on the user's role, it will return a :any:`Profile` for an investor or a :any:`BorrowersProfile` for a borrower. None for a financial institution

        :param user: The user whose profile has to be loaded.
        :type user: :any:`User`
        :return: :any:`Profile` or :any:`BorrowersProfile` or None
        """
        user = self._get_user(user)
        try:
            role = Role(user.role_id)

            if role.name == 'INVESTOR':
                profile = self.db.get(Profile._type, user.profile_id)
            elif role.name == 'BORROWER':
                profile = self.db.get(BorrowersProfile._type, user.profile_id)
            else:
                profile = None
        except AttributeError:
            profile = None

        return profile

    def place_loan_offer(self, investor, payload):
        """
        Create a loan offer by an investor and save it to the database. This offer will always be created with status as 'PENDING' as the borrower involved is the only one
        allowed to change the status of the loan offer.

        The payload contains the following data:

        +----------------+-----------------------------------------------------------+
        | Key            | Description                                               |
        +================+===========================================================+
        | amount         | The amount being invested                                 |
        +----------------+-----------------------------------------------------------+
        | duration       | The duration of the loan in months                        |
        +----------------+-----------------------------------------------------------+
        | interest_rate  | The interest due to be paid over the loan                 |
        +----------------+-----------------------------------------------------------+
        | mortgage_id    | The id of the mortgage being financed                     |
        +----------------+-----------------------------------------------------------+


        :param investor: The investor wishing to invest in a mortgage by placing a loan offer.
        :type investor: :any:`User`
        :param payload: The payload containing the data for the :any:`Investment`, as described above.
        :type payload: dict
        :return: The loan offer if successful or False.
        :rtype: :any:`Investment` or False
        """
        assert isinstance(investor, User)
        assert isinstance(payload, dict)

        role = Role(investor.role_id)

        if role.name == 'INVESTOR':
            investment = Investment(investor.id, payload['amount'], payload['duration'], payload['interest_rate'],
                                    payload['mortgage_id'], STATUS.PENDING)

            # Update the investor
            investment_id = self.db.post(Investment._type, investment)
            investor.investment_ids.append(investment_id)

            # Save the updated investor
            self.db.put(User._type, investor.id, investor)

            # Update the mortgage
            mortgage = self.db.get(Mortgage._type, payload['mortgage_id'])
            mortgage.investors.append(investor.id)
            self.db.put(Mortgage._type, mortgage.id, mortgage)

            # Update the borrower
            loan_request = self.db.get(LoanRequest._type, mortgage.request_id)
            borrower = self.db.get(User._type, loan_request.user_key)
            borrower.investment_ids.append(investment.id)
            self.db.put(User._type, borrower.id, borrower)

            # Add message to queue
            borrower = self.db.get(User._type, borrower.id)
            self.queue.add_message(self.community.send_investment_offer, [Investment._type], {Investment._type : investment}, [borrower])

            return investment
        else:
            return False

    def resell_investment(self):
        """
        Resell an invesment

        Not implemented yet.

        :raise: `NotImplementedError`
        """
        raise NotImplementedError

    def load_investments(self, user):
        """
        Get the pending and current investments list from the database.

        :param user: The user whose investments need to be retrieved.
        :type user: :any:`User`
        :return: A list containing lists with the list investments, the house, and the campaign
        :rtype: list
        """
        user = self._get_user(user)

        investments = []

        for investment_id in user.investment_ids:
            investment = self.db.get(Investment._type, investment_id)
            assert isinstance(investment, Investment)
            if investment.status == STATUS.ACCEPTED or investment.status == STATUS.PENDING:
                mortgage = self.db.get(Mortgage._type, investment.mortgage_id)
                house = self.db.get(House._type, mortgage.house_id)
                campaign = self.db.get(Campaign._type, mortgage.campaign_id)
                investments.append([investment, house, campaign])
        return investments

    def load_open_market(self):
        """
        Returns a list of all mortgages that have an active campaign going on.

        :return: A list lists with :any:`Mortgage` objects, :any: 'House' objects, and :any: 'Campaign' objects.
        :rtype: list
        """
        campaigns = self.db.get_all(Campaign._type)
        mortgages = []

        if campaigns:
            # If campaign is not completed or end time has not passed yet, get mortgage info
            for campaign in campaigns:
                if campaign.end_date > datetime.now() and not campaign.completed:
                    mortgage = self.db.get(Mortgage._type, campaign.mortgage_id)
                    house = self.db.get(House._type, mortgage.house_id)
                    mortgages.append([mortgage, campaign, house])

        return mortgages

    def get_role(self, user):
        """
        Get the role of the user from the database.

        :param user: The :any:`User` whose role you want to retrieve
        :return: : Returns the role or None.
        :rtype: :any:`User` or `None`
        """
        return Role(user.role_id)

    def create_loan_request(self, user, payload):
        """
        Create a Loan request for the given user using the payload provided.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | postal_code    | The postal code of the house that is the target of the mortgage  |
        +----------------+------------------------------------------------------------------+
        | house_number   | The house number of the house that is the target of the mortgage |
        +----------------+------------------------------------------------------------------+
        | price          | The total price of the house                                     |
        +----------------+------------------------------------------------------------------+
        | mortgage_type  | The mortgage type: 1 = linear, 2 = fixed-rate                    |
        +----------------+------------------------------------------------------------------+
        | banks          | List of banks the request should be sent to                      |
        +----------------+------------------------------------------------------------------+
        | description    | Free text (unicode)                                              |
        +----------------+------------------------------------------------------------------+
        | amount_wanted  | The amount the borrower wants financed                           |
        +----------------+------------------------------------------------------------------+

        :param user: The user creating a loan request
        :type user: :any:`User`
        :param payload: The payload containing the data for the :any:`House` and :any:`LoanRequest`, as described above.
        :type payload: dict
        :return: The loan request object if succesful or False
        :rtype: :any:`LoanRequest` or False
        """
        assert isinstance(user, User)
        assert isinstance(payload, dict)

        role = Role(user.role_id)

        # Only create a loan request if the user is a borrower
        if role.name == 'BORROWER':
            if not user.loan_request_ids:
                # Create the house
                house = House(payload['postal_code'], payload['house_number'], payload['price'])
                house_id = self.db.post(House._type, house)
                payload['house_id'] = house_id

                # Set status of the loan request (which is a dictionary of the banks) to pending
                payload['status'] = dict().fromkeys(payload['banks'], STATUS.PENDING)

                loan_request = LoanRequest(user.id, house_id, payload['house_link'], payload['seller_phone_number'], payload['seller_email'],
                                           payload['mortgage_type'], payload['banks'], payload['description'], payload['amount_wanted'], payload['status'])

                # Add the loan request to the borrower
                user.loan_request_ids.append(self.db.post(LoanRequest._type, loan_request))
                self.db.put(User._type, user.id, user)

                # Compile the candidates list
                candidates = []
                # Add the loan request to the banks' pending loan request list
                banks = []
                for bank_id in payload['banks']:
                    bank = self.db.get(User._type, bank_id)
                    if bank.id in self.user_candidate:
                        candidates.append(self.user_candidate[bank_id])

                    assert isinstance(bank, User)
                    bank.loan_request_ids.append(loan_request.id)
                    self.db.put(User._type, bank.id, bank)
                    banks.append(bank)

                # Add message to queue
                profile = self.db.get(Profile._type, user.profile_id)
                self.queue.add_message(self.community.send_loan_request, [LoanRequest._type, House._type, BorrowersProfile._type], {LoanRequest._type : loan_request, House._type : house, BorrowersProfile._type : profile}, banks)

                return loan_request

            else:
                return False
        else:
            return False

    def load_borrowers_loans(self, user):
        """
        Get the borrower's current active loans (funding goal has been reached) or the not yet active loans (funding goal has not been reached yet)
        :param user: User-object, in this case the user has the role of a borrower
        :return: list of the loans, containing either the current active loans or the not yet active loans
        """
        user = self._get_user(user)
        loans = []
        for mortgage_id in user.mortgage_ids:
            if self.db.get(Mortgage._type, mortgage_id).status == STATUS.ACCEPTED:
                mortgage = self.db.get(Mortgage._type, mortgage_id)
                # Add the accepted mortgage in the loans list
                loans.append(mortgage)
                campaign = self.db.get(Campaign._type, user.campaign_ids[0])
                for investor_id in mortgage.investors:
                    investor = self.db.get(User._type, investor_id)
                    for investment_id in investor.investment_ids:
                        investment = self.db.get(Investment._type, investment_id)
                        # Add the loan to the loans list if the investment has been accepted by the borrower and the mortgage id's match
                        if investment.status == STATUS.ACCEPTED and investment.mortgage_id == mortgage_id:
                            loans.append(investment)

        return loans

    def load_borrowers_offers(self, user):
        """
        Get all the borrower's offers(mortgage offers or loan offers) from the database.
        :param user: User-object, in this case the user has the role of a borrower
        :return: list of offers, containing either mortgage offers or investment offers
        :rtype: list
        """
        # Reload the user to get the latest data from the database.
        user = self._get_user(user)
        offers = []
        for mortgage_id in user.mortgage_ids:
            mortgage = self.db.get(Mortgage._type, mortgage_id)
            # If the mortgage is already accepted, we get the loan offers from the investors
            if mortgage.status == STATUS.ACCEPTED:
                for investor_id in mortgage.investors:
                    investor = self.db.get(User._type, investor_id)
                    for investment_id in investor.investment_ids:
                        investment = self.db.get(Investment._type, investment_id)
                        if investment.status == STATUS.PENDING:
                            offers.append(investment)

                return offers
            # If the mortgage has not yet been accepted, get the mortgage offers from the banks
            elif mortgage.status == STATUS.PENDING:
                offers.append(mortgage)

        return offers

    def create_campaign(self, user, mortgage, loan_request):
        """
        Create a funding campaign with crowdfunding goal the difference between the price of the house and the amount requested from the bank.
        #TODO: Should it be more flexible?

        :param user: The :any:`User` for who the mortgage is being made
        :type user: :any:`User`
        :param mortgage: The :any:`Mortgage` pertaining to the house being financed
        :type: mortgage: :any:`Mortgage`
        :param loan_request: The :any:`LoanRequest` created prior to the mortgage being accepted.
        :type loan_request: :any:`LoanRequest`
        :return: True if created, None otherwise.
        :rtype: bool or None
        """
        bank = self._get_user(mortgage.bank)
        house = self.db.get(House._type, mortgage.house_id)

        # Add the newly created campaign to the database
        end_date = datetime.now() + timedelta(days=CAMPAIGN_LENGTH_DAYS)
        finance_goal = house.price - mortgage.amount

        campaign = Campaign(mortgage.id, finance_goal, end_date, False)
        if self.db.post(Campaign._type, campaign):
            user.campaign_ids.append(campaign.id)
            bank.campaign_ids.append(campaign.id)
            self.db.put(User._type, bank.id, bank)
            mortgage.campaign_id = campaign.id
            self.db.put(Mortgage._type, mortgage.id, mortgage)

            # Add message to queue
            self.queue.add_message(self.community.send_mortgage_accept_signed, [Mortgage._type, Campaign._type], {Mortgage._type : mortgage, Campaign._type : campaign}, [bank])
            self.queue.add_message(self.community.send_mortgage_accept_unsigned, [Mortgage._type, Campaign._type], {Mortgage._type : mortgage, Campaign._type : campaign}, [])

            return self.db.put(User._type, user.id, user)
        return False

    def accept_mortgage_offer(self, user, payload):
        """
        Accept a mortgage offer for the given user.

        This action automatically rejects all other mortgage offers.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | mortgage_id    | The id of the mortgage                                           |
        +----------------+------------------------------------------------------------------+


        :param user: The user accepting a mortgage offer
        :type user: :any:`User`
        :param payload: The payload containing the data for the :any:`Mortgage`, as described above.
        :type payload: dict
        :return: Returns True if successful, False otherwise.
        :rtype: bool
        """
        mortgage = self.db.get(Mortgage._type, payload['mortgage_id'])
        assert isinstance(mortgage, Mortgage)
        loan_request = self.db.get(LoanRequest._type, mortgage.request_id)
        assert isinstance(loan_request, LoanRequest)

        loan_request.status[mortgage.bank] = STATUS.ACCEPTED
        mortgage.status = STATUS.ACCEPTED
        user.mortgage_ids.append(mortgage.id)

        # Reject the other banks
        for bank in loan_request.status:
            if not bank == mortgage.bank:
                loan_request.status[bank] = STATUS.REJECTED

        # Save the objects
        self.db.put(Mortgage._type, mortgage.id, mortgage)
        self.db.put(LoanRequest._type, loan_request.id, loan_request)
        self.db.put(User._type, user.id, user)

        # Create the campaign
        return self.create_campaign(user, mortgage, loan_request)

    def accept_investment_offer(self, user, payload):
        """
        Accept an investment offer for the given user.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | investment_id  | The id of the investment                                         |
        +----------------+------------------------------------------------------------------+

        :param user: The user accepting an investment offer.
        :type user: :any:`User`
        :param payload: The payload containing the data for the :any:`Investment`, as described above.
        :type payload: dict
        :return: Returns True if successful, False otherwise.
        :rtype: bool
        :raise: AssertionError if the user does not have a campaign assigned.
        """
        user = self._get_user(user)

        investment = self.db.get(Investment._type, payload['investment_id'])
        assert isinstance(investment, Investment)

        campaign = None
        if len(user.campaign_ids) == 0:
            raise AssertionError("The user does not have a campaign")

        for campaign_id in user.campaign_ids:
            campaign = self.db.get(Campaign._type, campaign_id)
            assert isinstance(campaign, Campaign)
            if investment.mortgage_id == campaign.mortgage_id:
                break

        if campaign:
            investment.status = STATUS.ACCEPTED
            campaign.subtract_amount(investment.amount)
            self.db.put(Investment._type, investment.id, investment)

            # Add message to queue
            investor = self.db.get(User._type, investment.investor_key)
            self.queue.add_message(self.community.send_investment_accept, [Investment._type], {Investment._type : investment}, [investor])

            return self.db.put(Campaign._type, campaign.id, campaign)
        return False

    def reject_mortgage_offer(self, user, payload):
        """
        Decline a mortgage offer for the given user.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | mortgage_id    | The id of the mortgage                                           |
        +----------------+------------------------------------------------------------------+


        :param user: The user rejecting a mortgage offer
        :type user: :any:`User`
        :param payload: The payload containing the data for the :any:`Mortgage`, as described above.
        :type payload: dict
        :return: Returns True if successful, False otherwise.
        :rtype: bool
        """
        user = self._get_user(user)
        mortgage = self.db.get(Mortgage._type, payload['mortgage_id'])
        loan_request = self.db.get(LoanRequest._type, mortgage.request_id)

        mortgage.status = STATUS.REJECTED
        loan_request.status[mortgage.bank] = STATUS.REJECTED
        user.mortgage_ids.remove(mortgage.id)
        self.db.put(Mortgage._type, mortgage.id, mortgage)

        # Add message to queue
        bank = self.db.get(User._type, mortgage.bank)
        self.queue.add_message(self.community.send_mortgage_reject, [Mortgage._type], {Mortgage._type : mortgage}, [bank])

        return self.db.put(LoanRequest._type, loan_request.id, loan_request) and self.db.put(User._type, user.id, user)

    def reject_investment_offer(self, user, payload):
        """
        Decline an investment offer for the given user.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | investment_id  | The id of the investment                                         |
        +----------------+------------------------------------------------------------------+

        :param user: The user rejecting an investment offer.
        :type user: :any:`User`
        :param payload: The payload containing the data for the :any:`Investment`, as described above.
        :type payload: dict
        :return: Returns True if successful, False otherwise.
        :rtype: bool
        """
        investment = self.db.get(Investment._type, payload['investment_id'])

        investment.status = STATUS.REJECTED
        self.db.put(Investment._type, investment.id, investment)

        # Add message to queue
        investor = self.db.get(User._type, investment.investor_key)
        self.queue.add_message(self.community.send_investment_reject, [Investment._type], {Investment._type : investment}, [investor])

        return investment

    def load_all_loan_requests(self, user):
        """
        Display all pending loan requests for the specific bank

        :param user: The bank :any:`User`
        :type user: :any:`User`
        :return: A list of lists containing the :any: 'LoanRequest's and the :any: 'House's
        :rtype: list
        """
        assert isinstance(user, User)

        user = self._get_user(user)

        pending_loan_requests = []

        # Only show loan requests that are still pending
        for pending_loan_request_id in user.loan_request_ids:
            if self.db.get(LoanRequest._type, pending_loan_request_id).status[user.id] == STATUS.PENDING:
                pending_loan_request = self.db.get(LoanRequest._type, pending_loan_request_id)
                house = self.db.get(House._type, pending_loan_request.house_id)
                pending_loan_requests.append([pending_loan_request, house])

        return pending_loan_requests

    def load_single_loan_request(self, payload):
        """
        Display the selected pending loan request

        :return: The :any: 'LoanRequest's
        :rtype: LoanRequest
        """
        assert isinstance(payload, dict)

        loan_request = self.db.get(LoanRequest._type, payload['loan_request_id'])
        assert isinstance(loan_request, LoanRequest)

        return loan_request

    def accept_loan_request(self, bank, payload):
        """
        Have the loan request passed by the payload be accepted by the bank calling the function.

        The payload is as follows:

        +-------------------+---------------------------------------------------------------+
        | Key               | Description                                                   |
        +===================+===============================================================+
        | request_id        | The :any:`LoanRequest` id                                     |
        +-------------------+---------------------------------------------------------------+
        | amount            | The amount the bank is willing to finance                     |
        +-------------------+---------------------------------------------------------------+
        | mortgage_type     | The mortgage type: 1 = linear, 2 = fixed-rate                 |
        +-------------------+---------------------------------------------------------------+
        | interest_rate     | The interest rate to be paid over the financed amount (float) |
        +-------------------+---------------------------------------------------------------+
        | default_rate      | The default rate (float)                                      |
        +-------------------+---------------------------------------------------------------+
        | max_invest_rate   | The maximum investment interest rate (float)                  |
        +-------------------+---------------------------------------------------------------+
        | duration          | The duration of the mortgage                                  |
        +-------------------+---------------------------------------------------------------+
        | investors         | List of initial investors, can be empty.                      |
        +-------------------+---------------------------------------------------------------+

        :param bank: The bank accepting the loan request.
        :type bank: :any:`User`
        :param payload: The payload containing the data for the :any:`Mortgage`, as described above.
        :type payload: dict
        :return: Returns the loan request and the mortgage objects, or None if an error occurs.
        :rtype: tuple(LoanRequest, Mortgage) or None
        """
        assert isinstance(bank, User)
        assert isinstance(payload, dict)
        assert self.get_role(bank).name == 'FINANCIAL_INSTITUTION'

        # Accept the loan request
        loan_request = self.db.get(LoanRequest._type, payload['request_id'])
        assert isinstance(loan_request, LoanRequest)
        loan_request.status[bank.id] = STATUS.ACCEPTED

        # Create a mortgage
        mortgage = Mortgage(loan_request.id, loan_request.house_id, bank.id, payload['amount'], payload['mortgage_type'], payload['interest_rate'], payload['max_invest_rate'],
                            payload['default_rate'], payload['duration'], payload['risk'], payload['investors'], STATUS.PENDING)
        borrower = self.db.get(User._type, payload['user_key'])
        assert isinstance(borrower, User)

        # Add mortgage to borrower
        self.db.post(Mortgage._type, mortgage)
        borrower.mortgage_ids.append(mortgage.id)
        self.db.put(User._type, borrower.id, borrower)

        # Add mortgage to bank
        bank.mortgage_ids.append(mortgage.id)
        self.db.put(User._type, bank.id, bank)

        # Save the accepted loan request
        if self.db.put(LoanRequest._type, loan_request.id, loan_request):
            # Add message to queue
            borrower = self.db.get(User._type, borrower.id)
            self.queue.add_message(self.community.send_mortgage_offer, [LoanRequest._type, Mortgage._type], {LoanRequest._type : loan_request, Mortgage._type : mortgage}, [borrower])

            return loan_request, mortgage
        else:
            return None

    # TODO: Add a way to signal events to Users
    def reject_loan_request(self, user, payload):
        """
        Decline an investment offer for the given user.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | request_id     | The id of the loan request                                       |
        +----------------+------------------------------------------------------------------+

        :param user: The bank rejecting a loan request.
        :type user: :any:`User`
        :param payload: The payload containing the data for the :any:`LoanRequest`, as described above.
        :type payload: dict
        :return: Returns the rejected :any: 'LoanRequest' if successful, None otherwise.
        :rtype: LoanRequest or None
        """
        assert isinstance(user, User)
        assert isinstance(payload, dict)

        # Reject the loan request
        rejected_loan_request = self.db.get(LoanRequest._type, payload['request_id'])
        assert isinstance(rejected_loan_request, LoanRequest)
        rejected_loan_request.status[user.id] = STATUS.REJECTED

        # Save rejected loan request
        borrower = self.db.get(User._type, rejected_loan_request.user_key)
        assert isinstance(borrower, User)
        loan_request_id = borrower.loan_request_ids[0]

        # Remove the loan request from the bank's list
        user.loan_request_ids.remove(loan_request_id)

        # Check if the loan request has been rejected by all selected banks
        rejected = True
        for bank in rejected_loan_request.status:
            if rejected_loan_request.status[bank] != STATUS.REJECTED:
                rejected = False

        # If all banks have rejected the loan request, remove the loan request from borrower
        if rejected:
            borrower.loan_request_ids.remove(loan_request_id)
            self.db.put(User._type, borrower.id, borrower)

        # Save the rejected loan request
        if self.db.put(LoanRequest._type, loan_request_id, rejected_loan_request):
            # Add message to queue
            borrower = self.db.get(User._type, borrower.id)
            self.queue.add_message(self.community.send_loan_request_reject, [LoanRequest._type], {LoanRequest._type : rejected_loan_request}, [borrower])

            return rejected_loan_request
        else:
            return None

    def load_bids(self, payload):
        """ Returns a list of all bids on the selected campaign.

        The payload dictionary has the following composition

        +----------------+------------------------------------------------------------------+
        | Key            | Description                                                      |
        +================+==================================================================+
        | mortgage_id    | The id of the selected mortgage                                  |
        +----------------+------------------------------------------------------------------+

        :param payload: The payload containing the data for the :any:`Investment`, as described above.
        :type payload: dict
        :return: A list of lists with :any: 'Investment' objects, a :any: 'House' object, a :any: 'Campaign' object.
        :rtype: list
        """

        # Get the list of all the bids (pending/accepted/rejected) on the campaign
        mortgage = self.db.get(Mortgage._type, payload['mortgage_id'])
        loan_request = self.db.get(LoanRequest._type, mortgage.request_id)
        borrower = self.db.get(User._type, loan_request.user_key)

        bids = []
        for investment_bid in borrower.investment_ids:
            bids.append(self.db.get(Investment._type, investment_bid))

        house = self.db.get(House._type, loan_request.house_id)
        campaign = self.db.get(Campaign._type, borrower.campaign_ids[0])

        return bids, house, campaign

    def load_mortgages(self, user):
        """
            Display all pending running mortgages for the bank

            :param user: The bank :any:`User`
            :type user: :any:`User`
            :return: A list of lists containing the :any: 'Mortgage', the :any: 'House', and the :any: 'Campaign'
            :rtype: list
        """
        assert isinstance(user, User)
        user = self._get_user(user)

        mortgages = []

        for mortgage_id in user.mortgage_ids:
            mortgage = self.db.get(Mortgage._type, mortgage_id)
            assert isinstance(mortgage, Mortgage)
            if mortgage.status == STATUS.ACCEPTED:
                house = self.db.get(House._type, mortgage.house_id)
                campaign = self.db.get(Campaign._type, mortgage.campaign_id)
                mortgages.append([mortgage, house, campaign])

        return mortgages
