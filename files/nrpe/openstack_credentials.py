# Helper class for authenticating against Keystone and getting OpenStack API
# objects.
#
# Authors:
#  Risto Laurikainen
#  Jukka Nousiainen
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as keystone_client
from novaclient import client as nova_client
from cinderclient import client as cinder_client

class OpenStackCredentials(object):

    def __init__(self,
                 auth_url,
                 username,
                 password,
                 project_id,
                 project_name,
                 domain_id):
        self.auth_url = auth_url
        self.username = username
        self.password = password
        self.project_id = project_id
        self.project_name = project_name
        self.domain_id = domain_id
        self.auth = v3.Password(auth_url=self.auth_url,
                                username=self.username,
                                password=self.password,
                                project_id=self.project_id,
                                user_domain_id=self.domain_id)
        self.session = session

    def get_keystone(self):
        sess = self.session.Session(auth=self.auth)
        keystone = keystone_client.Client(session=sess)

        return keystone

    def get_nova(self):
        sess = self.session.Session(auth=self.auth)
        nova = nova_client.Client(2, session=sess)

        return nova

    def get_cinder(self):
        sess = self.session.Session(auth=self.auth)
        cinder = cinder_client.Client(2, session=sess)

        return cinder
