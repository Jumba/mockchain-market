import socket
import os
import glob
import ntpath
import tftpy
from tftpy import TftpClient
from threading import Thread
import time
import logging

RESOURCES_PATH = '/resources/received/'


class Client:
    def __init__(self):
        self.resources = None
        tftpy.setLogLevel('INFO')
        fh = logging.FileHandler(os.getcwd()+'/logging/log_client_'+time.strftime('%d-%m-%Y_%H:%M:%S'))
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        tftpy.log.addHandler(fh)
        self.client = TftpClient(socket.gethostbyname(socket.gethostname()), 50000)
        self.sent_files = []
        self.files = []
        self.failed_to_send = []
        # self.thread = Thread

    def upload(self, local_file_name, remote_file_name=None):
        if not remote_file_name:
            remote_file_name = RESOURCES_PATH + ntpath.basename(local_file_name)
        try:
            self.client.upload(remote_file_name, local_file_name)
            self.sent_files.append(local_file_name)
        except:
            print 'Uploading of ', remote_file_name, ' failed.'
            self.failed_to_send.append(remote_file_name)
            raise

    def download(self, remote_file_name, local_file_name=None):
        if not local_file_name:
            local_file_name = RESOURCES_PATH + ntpath.basename(remote_file_name)
        try:
            self.client.download(local_file_name, remote_file_name)
        except:
            raise

    # def upload(self, local_file_name, remote_file_name):
    #     if self.thread.is_alive():
    #         print 'The thread is busy.'
    #     else:
    #         self.thread = Thread(target=self.upload_to_server(local_file_name, remote_file_name))
    #         self.thread.start()
    #
    # def download(self, remote_file_name, local_file_name):
    #     if self.thread.is_alive():
    #         print 'The thread is busy.'
    #     else:
    #         self.thread = Thread(target=self.download_from_server(remote_file_name, local_file_name))
    #         self.thread.start()

    def upload_folder(self, path=os.getcwd()+'/resources'):
        self.files = glob.glob(path+'/*.pdf')
        print self.files
        for f in self.files:
            self.upload(f)

if __name__ == '__main__':
    tc = Client()
    # tc.upload('server.pdf', 'downloaded.pdf')
    # tc.thread.target = tc.upload_folder
    thread = Thread(target=tc.upload_folder())
    thread.start()


