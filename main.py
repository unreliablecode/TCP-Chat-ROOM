import select
import socket
import sys
import signal
import pickle
import struct
import argparse

SERVER_HOST = 'localhost'
CHAT_SERVER_NAME = 'server'

class ChatRoom:
    def __init__(self, name):
        self.name = name
        self.clients = []

    def join(self, client):
        if client not in self.clients:
            self.clients.append(client)

    def leave(self, client):
        if client in self.clients:
            self.clients.remove(client)

class ChatServer(object):
    def __init__(self, port, backlog=5):
        self.clients = 0
        self.clientmap = {}
        self.outputs = []
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((SERVER_HOST, port))
        print ('Server listening to port: %s ...' % port)
        self.server.listen(backlog)
        signal.signal(signal.SIGINT, self.sighandler)
        self.rooms = {}  # Dictionary to store chat rooms

    def sighandler(self, signum, frame):
        print ('Shutting down server...')
        for output in self.outputs:
            output.close()
        self.server.close()

    def get_client_name(self, client):
        info = self.clientmap[client]
        host, name = info[0][0], info[1]
        return '@'.join((name, host))

    def create_or_join_room(self, client, room_name):
        if room_name not in self.rooms:
            self.rooms[room_name] = ChatRoom(room_name)
        self.rooms[room_name].join(client)

    def get_room_of_client(self, client):
        for room in self.rooms.values():
            if client in room.clients:
                return room
        return None

    def run(self):
        inputs = [self.server, sys.stdin]
        self.outputs = []
        running = True

        while running:
            try:
                readable, writeable, exceptional = select.select(inputs, self.outputs, [])
            except select.error as e:
                break

            for sock in readable:
                if sock == self.server:
                    client, address = self.server.accept()
                    print ("Chat server: got connection %d from %s" % (client.fileno(), address))
                    cname = receive(client).split('NAME: ')[1]
                    room_name = receive(client).split('ROOM: ')[1]
                    self.clients += 1
                    send(client, 'CLIENT: ' + str(address[0]))
                    inputs.append(client)
                    self.clientmap[client] = (address, cname)

                    self.create_or_join_room(client, room_name)
                    room = self.get_room_of_client(client)

                    msg = "\n(Connected: New client (%d) in room %s from %s)" % (
                        self.clients, room_name, self.get_client_name(client))

                    for c in room.clients:
                        send(c, msg)

                    self.outputs.append(client)
                elif sock == sys.stdin:
                    junk = sys.stdin.readline()
                    running = False
                else:
                    try:
                        data = receive(sock)
                        if data:
                            room = self.get_room_of_client(sock)
                            if room:
                                msg = '\n#[' + self.get_client_name(sock) + ']>>' + data
                                for output in room.clients:
                                    if output != sock:
                                        send(output, msg)
                        else:
                            print ("Chat server: %d hung up" % sock.fileno())
                            self.clients -= 1
                            sock.close()
                            inputs.remove(sock)
                            self.outputs.remove(sock)
                            msg = "\n(Now hung up: Client from %s)" % self.get_client_name(sock)
                            for output in self.outputs:
                                send(output, msg)
                    except socket.error as e:
                        inputs.remove(sock)
                        self.outputs.remove(sock)
        self.server.close()

class ChatClient(object):
    def __init__(self, name, port, room, host=SERVER_HOST):
        self.name = name
        self.connected = False
        self.host = host
        self.port = port
        self.room = room
        self.prompt = '[' + '@'.join((name, socket.gethostname().split('.')[0])) + ']> '

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, self.port))
            print (f"Now connected to chat server {SERVER_HOST} @ port %d" % self.port)
            self.connected = True
            send(self.sock, 'NAME: ' + self.name)
            send(self.sock, 'ROOM: ' + self.room)
            data = receive(self.sock)
            addr = data.split('CLIENT: ')[1]
            self.prompt = '[' + '@'.join((self.name, addr)) + ']> '
        except socket.error as e:
            print (f"Failed to connect to chat server {SERVER_HOST} @ port %d" % self.port)
            sys.exit(1)

    def run(self):
        while self.connected:
            try:
                sys.stdout.write(self.prompt)
                sys.stdout.flush()

                readable, writeable, exceptional = select.select([0, self.sock], [], [])
                for sock in readable:
                    if sock == 0:
                        data = sys.stdin.readline().strip()
                        if data:
                            send(self.sock, data)
                    elif sock == self.sock:
                        data = receive(self.sock)
                    if not data:
                        print ('Client shutting down.')
                        self.connected = False
                        break
                    else:
                        sys.stdout.write(data + '\n')
                        sys.stdout.flush()
            except KeyboardInterrupt:
                print ("Client interrupted.")
                self.sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Socket Server Example with Select')
    parser.add_argument('--name', action="store", dest="name", required=True)
    parser.add_argument('--port', action="store", dest="port", type=int, required=True)
    parser.add_argument('--room', action="store", dest="room", required=True)
    given_args = parser.parse_args()
    port = given_args.port
    name = given_args.name
    room = given_args.room

    if name == CHAT_SERVER_NAME:
        server = ChatServer(port)
        server.run()
    else:
        client = ChatClient(name=name, port=port, room=room)
        client.run()
