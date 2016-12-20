import logging
import time

from conversion import MortgageMarketConversion
from market.api.api import STATUS
from market.dispersy.authentication import MemberAuthentication, DoubleMemberAuthentication
from market.dispersy.community import Community
from market.dispersy.conversion import DefaultConversion
from market.dispersy.destination import CommunityDestination, CandidateDestination
from market.dispersy.distribution import DirectDistribution, FullSyncDistribution
from market.dispersy.message import Message, DelayMessageByProof
from market.dispersy.resolution import PublicResolution
from market.models import DatabaseModel
from market.models.house import House
from market.models.loans import LoanRequest, Mortgage, Campaign, Investment
from market.models.profiles import BorrowersProfile
from market.models.user import User
from payload import DatabaseModelPayload, ModelRequestPayload, APIMessagePayload, SignedConfirmPayload

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MortgageMarketCommunity(Community):
    @classmethod
    def get_master_members(cls, dispersy):
        master_key = "3081a7301006072a8648ce3d020106052b8104002703819200040578e79f08d3270c5af04ace5b572ecf46eef54502c1" \
                     "4f3dc86f4cd29e86f05dad976b08da07b8d97d73fc8243459e09b6b208a2c8cbf6fdc7b78ae2668606388f39ef0fa715cf2" \
                     "104ad21f1846dd8f93bb25f2ce785cced2c9231466a302e5f9e0e70f72a3a912f2dae7a9a38a5e7d00eb7aef23eb42398c38" \
                     "59ffadb28ca28a1522addcaa9be4eec13095f48f7cf35".decode("HEX")

        master = dispersy.get_member(public_key=master_key)
        return [master]

    def __init__(self, dispersy, master, my_member):
        super(MortgageMarketCommunity, self).__init__(dispersy, master, my_member)
        self._api = None
        self._user = None

    def initialize(self):
        super(MortgageMarketCommunity, self).initialize()
        logger.info("Example community initialized")

    def on_introduction_response(self, messages):
        super(MortgageMarketCommunity, self).on_introduction_response(messages)
        for message in messages:
            self.send_introduce_user(['user', ], {'user': self.user}, message.candidate)

    def initiate_meta_messages(self):
        return super(MortgageMarketCommunity, self).initiate_meta_messages() + [
            Message(self, u"model_request",
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CommunityDestination(node_count=50),
                    ModelRequestPayload(),
                    self.check_message,
                    self.on_model_request),
            Message(self, u"model_request_response",
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    DatabaseModelPayload(),
                    self.check_message,
                    self.on_model_request_response),
            Message(self, u"introduce_user",
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    DatabaseModelPayload(),
                    self.check_message,
                    self.on_user_introduction),
            Message(self, u"api_message_community",
                    MemberAuthentication(),
                    PublicResolution(),
                    FullSyncDistribution(synchronization_direction=u"RANDOM", priority=127, enable_sequence_number=True),
                    CommunityDestination(node_count=50),
                    APIMessagePayload(),
                    self.check_message,
                    self.on_api_message),
            Message(self, u"api_message_candidate",
                    MemberAuthentication(),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    APIMessagePayload(),
                    self.check_message,
                    self.on_api_message),
            Message(self, u"signed_confirm",
                    DoubleMemberAuthentication(
                        allow_signature_func=self.allow_signed_confirm),
                    PublicResolution(),
                    DirectDistribution(),
                    CandidateDestination(),
                    SignedConfirmPayload(),
                    self._generic_timeline_check,
                    self.received_signed_confirm),
        ]

    def initiate_conversions(self):
        return [DefaultConversion(self), MortgageMarketConversion(self)]

    def check_message(self, messages):
        for message in messages:
            allowed, _ = self._timeline.check(message)
            if allowed:
                yield message
            else:
                yield DelayMessageByProof(message)

    @property
    def api(self):
        return self._api

    @api.setter
    def api(self, api):
        self._api = api

    @property
    def user(self):
        return self._user

    @user.setter
    def user(self, user):
        self._user = user

    def send_api_message_candidate(self, request, fields, models, candidates, store=True, update=True, forward=True):
        assert isinstance(request, unicode)
        assert isinstance(fields, list)
        assert isinstance(models, dict)

        meta = self.get_meta_message(u"api_message_candidate")
        message = meta.impl(authentication=(self.my_member,),
                            distribution=(self.claim_global_time(),),
                            destination=candidates,
                            payload=(request, fields, models),
                            )
        self.dispersy.store_update_forward([message], store, update, forward)

    def send_api_message_community(self, request, fields, models, store=True, update=True, forward=True):
        assert isinstance(request, unicode)
        assert isinstance(fields, list)
        assert isinstance(models, dict)

        meta = self.get_meta_message(u"api_message_community")
        message = meta.impl(authentication=(self.my_member,),
                            distribution=(self.claim_global_time(), meta.distribution.claim_sequence_number()),
                            payload=(request, fields, models),
                            )
        self.dispersy.store_update_forward([message], store, update, forward)

    def on_api_message(self, messages):
        for message in messages:
            self.api.incoming_queue.push(message)

    def send_model_request(self, models, store=True, update=True, forward=True):
        assert isinstance(models, list)

        meta = self.get_meta_message(u"model_request")
        message = meta.impl(authentication=(self.my_member,),
                            distribution=(self.claim_global_time(),),
                            payload=(models,), )
        self.dispersy.store_update_forward([message], store, update, forward)

    def send_model_request_response(self, fields, models, candidates, store=True, update=True, forward=True):
        for field in fields:
            assert isinstance(models[field], DatabaseModel)

        meta = self.get_meta_message(u"model_request_response")
        message = meta.impl(authentication=(self.my_member,),
                            distribution=(self.claim_global_time(),),
                            payload=(fields, models,),
                            destination=candidates)
        self.dispersy.store_update_forward([message], store, update, forward)

    def send_introduce_user(self, fields, models, candidate, store=True, update=True, forward=True):
        for field in fields:
            assert isinstance(models[field], DatabaseModel)

        meta = self.get_meta_message(u"introduce_user")
        message = meta.impl(authentication=(self.my_member,),
                            distribution=(self.claim_global_time(),),
                            payload=(fields, models,),
                            destination=(candidate,))
        self.dispersy.store_update_forward([message], store, update, forward)

    #######################################
    ########### API MESSAGES

    def on_loan_request_receive(self, payload):
        user = payload.models[User._type]
        loan_request = payload.models[LoanRequest._type]
        house = payload.models[House._type]
        profile = payload.models[BorrowersProfile._type]

        assert isinstance(user, User)
        assert isinstance(loan_request, LoanRequest)
        assert isinstance(house, House)
        assert isinstance(profile, BorrowersProfile)

        user.post_or_put(self.api.db)
        loan_request.post_or_put(self.api.db)
        house.post_or_put(self.api.db)
        profile.post_or_put(self.api.db)

        # Save the loan request to the bank
        if self.user.id in loan_request.banks:
            self.user.update(self.api.db)
            self.user.loan_request_ids.append(loan_request.id)
            self.user.post_or_put(self.api.db)

        return True

    def on_loan_request_reject(self, payload):
        user = payload.models[User._type]
        loan_request = payload.models[LoanRequest._type]

        assert isinstance(user, User)
        assert isinstance(loan_request, LoanRequest)

        user.post_or_put(self.api.db)
        loan_request.post_or_put(self.api.db)

        # If not all banks have rejected the loan request, do nothing
        for _, status in loan_request.banks:
            if status == STATUS.ACCEPTED or status == STATUS.PENDING:
                return True

        # If all banks have rejected the loan request, remove the request from the borrower
        self.user.update(self.api.db)
        self.user.loan_request_ids = []
        self.user.post_or_put(self.api.db)

        return True

    def on_mortgage_offer(self, payload):
        loan_request = payload.models[LoanRequest._type]
        mortgage = payload.models[Mortgage._type]

        assert isinstance(loan_request, LoanRequest)
        assert isinstance(mortgage, Mortgage)

        loan_request.post_or_put(self.api.db)
        mortgage.post_or_put(self.api.db)

        # Add mortgage to the borrower
        self.user.update(self.api.db)
        if mortgage.id not in self.user.mortgage_ids:
            self.user.mortgage_ids.append(mortgage.id)
        self.user.post_or_put(self.api.db)

        return True

    def on_mortgage_accept_signed(self, payload):
        """
        This is a directed message to the bank. So now the bank starts the sign agreement procedure.
        :param payload:
        :return:
        """
        user = payload.models[User._type]
        mortgage = payload.models[Mortgage._type]
        campaign = payload.models[Campaign._type]

        assert isinstance(user, User)
        assert isinstance(campaign, Campaign)
        assert isinstance(mortgage, Mortgage)

        user.post_or_put(self.api.db)
        mortgage.post_or_put(self.api.db)
        campaign.post_or_put(self.api.db)

        # The bank can now initiate a signing step.
        if self.user.id == mortgage.bank:
            print "Signing the agreement"
            # resign because the status has been changed.
            self.publish_signed_confirm_message(user.id, mortgage)

        # Save the started campaign to the bank
        self.user.update(self.api.db)
        self.user.campaign_ids.append(campaign.id)
        self.user.post_or_put(self.api.db)

        return True

    def on_mortgage_accept_unsigned(self, payload):
        user = payload.models[User._type]
        loan_request = payload.models[LoanRequest._type]
        mortgage = payload.models[Mortgage._type]
        campaign = payload.models[Campaign._type]

        assert isinstance(user, User)
        assert isinstance(campaign, Campaign)
        assert isinstance(mortgage, Mortgage)
        assert isinstance(loan_request, LoanRequest)

        user.post_or_put(self.api.db)
        loan_request.post_or_put(self.api.db)
        mortgage.post_or_put(self.api.db)
        campaign.post_or_put(self.api.db)

        return True

    def on_mortgage_reject(self, payload):
        user = payload.models[User._type]
        mortgage = payload.models[Mortgage._type]

        assert isinstance(user, User)
        assert isinstance(mortgage, Mortgage)

        user.post_or_put(self.api.db)
        mortgage.post_or_put(self.api.db)

        # Remove the mortgage from the bank
        self.user.update(self.api.db)
        self.user.mortgage_ids.remove(mortgage.id)
        self.user.post_or_put(self.api.db)

        return True

    def on_investment_offer(self, payload):
        user = payload.models[User._type]
        investment = payload.models[Investment._type]

        assert isinstance(user, User)
        assert isinstance(investment, Investment)

        user.post_or_put(self.api.db)
        investment.post_or_put(self.api.db)

        # Save the investment to the borrower
        self.user.update(self.api.db)
        self.user.investment_ids.append(investment.id)
        self.user.post_or_put(self.api.db)

        return True

    def on_investment_accept(self, payload):
        user = payload.models[User._type]
        investment = payload.models[Investment._type]

        assert isinstance(user, User)
        assert isinstance(investment, Investment)

        user.post_or_put(self.api.db)
        investment.post_or_put(self.api.db)

        return True

    def on_investment_reject(self, payload):
        user = payload.models[User._type]
        investment = payload.models[Investment._type]

        assert isinstance(user, User)
        assert isinstance(investment, Investment)

        user.post_or_put(self.api.db)
        investment.post_or_put(self.api.db)

        # Remove the investment from the investor
        self.user.update(self.api.db)
        self.user.investment_ids.remove(investment.id)
        self.user.post_or_put(self.api.db)

        return True

    ########## END API MESSAGES

    def on_model_request(self, messages):
        for message in messages:
            # Payload is a dictionary with {type : uuid}
            for model_type, model_id in message.payload.models:
                obj = self.api.db.get(model_type, model_id)
                self.send_model_request_response([obj.id], {obj.id: obj})

    def on_model_request_response(self, messages):
        for message in messages:
            for field in message.payload.fields:
                obj = message.payload.models[field]
                self.api.db.post(obj.type, obj)

    def on_user_introduction(self, messages):
        for message in messages:
            for field in message.payload.fields:
                obj = message.payload.models[field]
                if isinstance(obj, User) and not obj == self.user:
                    # Banks need to be overwritten
                    if obj.role_id == 3:
                        self.api.db.put(obj.type, obj.id, obj)
                    else:
                        self.api.db.post(obj.type, obj)

                    # Add the candidate at the end to prevent a race condition where a message containing the user may be sent
                    # before the model is saved.
                    self.api.user_candidate[obj.id] = message.candidate

    ##############
    ##### SIGNED MESSAGES
    ###############

    def publish_signed_confirm_message(self, user_key, agreement):
        """
        Creates and sends out a signed signature_request message
        Returns true upon success
        """
        if user_key in self.api.user_candidate and isinstance(agreement, DatabaseModel):
            candidate = self.api.user_candidate[user_key]
            message = self.create_signed_confirm_request_message(candidate, agreement)
            self.create_signature_request(candidate, message, self.allow_signed_confirm_response)
            # TODO: Save on blockchain
            return True
        else:
            return False

    def create_signed_confirm_request_message(self, candidate, agreement):
        """

        """
        # Init the data being sent
        benefactor = self.user.id
        beneficiary = ''  # Target user fills it in themselves.
        timestamp = int(time.time())

        payload = (benefactor, beneficiary, agreement, timestamp)
        meta = self.get_meta_message(u"signed_confirm")

        message = meta.impl(authentication=([self.my_member, candidate.get_member()],),
                            distribution=(self.claim_global_time(),),
                            payload=payload)
        return message

    def allow_signed_confirm(self, message):
        """
        We've received a signature request message, we must either:
            a. Create and sign the response part of the message, send it back, and persist the block.
            b. Drop the message. (Future work: notify the sender of dropping)
            :param message The message containing the received signature request.
        """
        payload = message.payload

        agreement = payload.agreement
        agreement_local = self.api.db.get(agreement.type, agreement.id)

        if agreement == agreement_local:
            payload = (payload.benefactor, self.user.id, agreement, payload.time)
            meta = self.get_meta_message(u"signed_confirm")
            message = meta.impl(authentication=(message.authentication.members, message.authentication.signatures),
                                distribution=(message.distribution.global_time,),
                                payload=payload)
            # TODO: Save to blockchain
            return message
        else:
            return None

    def allow_signed_confirm_response(self, request, response, modified):
        """
        We've received a signature response message after sending a request, we must return either:
            a. True, if we accept this message
            b. False, if not (because of inconsistencies in the payload)
        """
        if not response:
            print "Timeout received for signature request."
            return False
        else:
            agreement = response.payload.agreement
            agreement_local = request.payload.agreement

            # TODO: Change the __eq__ function of DatabaseModel to do a deep compare.
            if agreement_local == agreement:
                if isinstance(agreement, Investment):
                    mortgage = self.api.db.get(Mortgage._type, agreement.mortgage_id)
                elif isinstance(agreement, Mortgage):
                    mortgage = agreement

                loan_request = self.api.db.get(LoanRequest._type, mortgage.request_id)
                beneficiary = self.api.db.get(User._type, loan_request.user_key)

                return (response.payload.beneficiary == beneficiary.id and response.payload.benefactor == self.user.id
                        and modified)
            else:
                return False

    def received_signed_confirm(self, messages):
        """
        We've received a valid signature response and must process this message.
        :param messages The received, and validated signature response messages
        """
        print "Valid %s signature response(s) received." % len(messages)
        for message in messages:
            print message.payload.agreement, " is official. Message signed = ", message.authentication.is_signed
