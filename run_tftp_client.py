import tftpy
import socket

client = tftpy.TftpClient(socket.gethostbyname(socket.gethostname()), 6969)
client.download('server.pdf', 'downloaded.pdf')