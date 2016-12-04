from market.models import DatabaseModel


class User(DatabaseModel):
    _type = 'users'

    def __init__(self, public_key, time_added, role_id=None, profile_id=None, loan_request_id=None, campaign_ids=None, mortgage_ids=None, investment_ids=None, pending_loan_request_ids=None):
        self._public_key = public_key
        self._time_added = time_added
        self._role_id = role_id
        self._profile_id = profile_id
        self._loan_request_id = loan_request_id
        self._campaign_ids = campaign_ids or []
        self._mortgage_ids = mortgage_ids or []
        self._investment_ids = investment_ids or []
        self._pending_loan_request_ids = pending_loan_request_ids or []

    @property
    def user_key(self):
        return self._public_key

    @property
    def time_added(self):
        return self._time_added

    @property
    def profile_id(self):
        return self._profile_id

    @property
    def loan_request_id(self):
        return self._loan_request_id

    @property
    def mortgage_ids(self):
        return self._mortgage_ids

    @property
    def investment_ids(self):
        return self._investment_ids

    @property
    def role_id(self):
        return self._role_id

    @property
    def campaign_ids(self):
        return self._campaign_ids

    def generate_id(self):
        return self.user_key

    @profile_id.setter
    def profile_id(self, value):
        self._profile_id = value

    @role_id.setter
    def role_id(self, value):
        self._role_id = value

    @loan_request_id.setter
    def loan_request_id(self, value):
        self._loan_request_id = value

    @property
    def pending_loan_request_ids(self):
        return self._pending_loan_request_ids
