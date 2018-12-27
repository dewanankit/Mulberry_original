from twisted.internet import reactor
from twisted.internet.protocol import Protocol
from twisted.internet.protocol import Factory
from twisted.internet.endpoints import TCP4ClientEndpoint
import sys
#from sys import stdout

class MulClient(Protocol):
    def __init__(self,ch):
        self.clienthandler=ch
        self.transport=self.transport

    def sendMessage(self, msg):
        self.transport.write(msg+";")
        sys.stdout.write("sent: " + msg + "\n")
    
    def dataReceived(self, data):
        for datum in data.split(";"):
            if datum is None or datum=="":
                continue
            sys.stdout.write("recv: " + datum + "\n")
            self.clienthandler.processFeedback(self, datum)

def connectProtocol(endpoint, protocol):
    class OneShotFactory(Factory):
        def buildProtocol(self, addr):
            return protocol
    return endpoint.connect(OneShotFactory())

class ClientHandler:
    # instance variable
    # remote: conn object that contains remote peer info
    # state: state object of my peer lists
    # mode: mode of operation
    # - join: initiates join request
    # - join2: sends peer a new joiner
    # - join3: sends new joiner a peer list
    # - join4: poll
    # - join5: forward join
    # - join6: send a peer list for the last level
    # - exit1: send exit message
    # - exit2: elect a leader
    # - exit3: poll peers at level above last
    # - exit4: request for a transfer at last level
    # - exit5: joining new group
    # - exit6: broadcast joiner
    # - exit7: reply to joiner a peer list
    # extra: extra argument usually contain a list to send out

    def __init__(self,state,conn,mode,extra=None):
        self.remote=conn
        self.state=state
        self.mode=mode
        self.extra=extra

    def startup(self):
        point=TCP4ClientEndpoint(reactor, self.remote.addr, self.remote.port)
        myclientprotocol=MulClient(self)
        d=connectProtocol(point, myclientprotocol)
        myclienthandler=self
        d.addCallback(myclienthandler.gotProtocol)

    def gotProtocol(self, p):
        #p.sendMessage("HELLO")
        if self.mode=='join':
            replymsg="JOIN_INIT "+self.state.myconn.name+" "+self.state.myconn.addr+" "+str(self.state.myconn.port)+" "+self.state.myconn.name
            p.sendMessage(replymsg)
        elif self.mode=='join2':
            replymsg="JOIN_BOTT "+self.state.myconn.name+" "+self.extra.addr+" "+str(self.extra.port)+" "+self.extra.name
            #reactor.callLater(1, p.sendMessage, replymsg)
            p.sendMessage(replymsg)
        elif self.mode=='join3':
            extra1,level=self.extra
            replymsg="JOIN_LIST "+self.state.myconn.name+" "+str(level)+" "+str(len(extra1))
            for conn in extra1:
                replymsg=replymsg+"\n"+conn.addr+" "+str(conn.port)+" "+conn.name
            p.sendMessage(replymsg)
        elif self.mode=='join4':
            # simply send request for info with joiner ip and address and name
            extra1,callback,level=self.extra
            replymsg="JOIN_POLL "+self.state.myconn.name+" "+extra1.addr+" "+str(extra1.port)+" "+extra1.name
            p.sendMessage(replymsg)
        elif self.mode=='join5':
            extra1,level=self.extra
            replymsg="JOIN_FRWD "+self.state.myconn.name+" "+extra1.addr+" "+str(extra1.port)+" "+extra1.name+" "+str(level)
            p.sendMessage(replymsg)
        elif self.mode=='join6':
            extra=self.extra
            replymsg="JOIN_LAST "+self.state.myconn.name+" "+str(len(extra))
            for conn in extra:
                replymsg=replymsg+"\n"+conn.addr+" "+str(conn.port)+" "+conn.name
            p.sendMessage(replymsg)
        elif self.mode=='exit1':
            # send over my detail and level i am on
            replymsg="EXIT_INIT "+self.state.myconn.name+" "+self.state.myconn.addr+" "+str(self.state.myconn.port)+" "+self.state.myconn.name+" "+str(self.extra)
            p.sendMessage(replymsg)
        elif self.mode=='exit2':
            replymsg="EXIT_ELCT "+self.state.myconn.name
            p.sendMessage(replymsg)
        elif self.mode=='exit3':
            replymsg="EXIT_POLL "+self.state.myconn.name
            p.sendMessage(replymsg)
        elif self.mode=='exit4':
            extra1,level,pos=self.extra
            replymsg="EXIT_FRWD "+self.state.myconn.name+" "+extra1.addr+" "+str(extra1.port)+" "+extra1.name+" "+str(level)+" "+str(pos)
            p.sendMessage(replymsg)
        elif self.mode=='exit5':
            replymsg="EXIT_JOIN "+self.state.myconn.name+" "+self.extra.addr+" "+str(self.extra.port)+" "+self.extra.name
            p.sendMessage(replymsg)
        elif self.mode=='exit6':
            extra=self.extra
            replymsg="EXIT_BRCT "+self.state.myconn.name+" "+extra.addr+" "+str(extra.port)+" "+extra.name
            p.sendMessage(replymsg)
        elif self.mode=='exit7':
            extra=self.extra
            replymsg="EXIT_LIST "+self.state.myconn.name+" "+str(len(extra))
            for conn in extra:
                replymsg=replymsg+"\n"+conn.addr+" "+str(conn.port)+" "+conn.name
            p.sendMessage(replymsg)
        else:
            p.transport.loseConnection()

    def processFeedback(self, protocol, data):
        if self.mode=='join':
            if data=="WAIT":
                protocol.sendMessage("JOIN_OKAY")
        elif self.mode=='join2':
            if data=="JOIN_OKAY":
                protocol.transport.loseConnection()
        elif self.mode=='join3':
            if data=="JOIN_OKAY":
                protocol.transport.loseConnection()
        elif self.mode=='join4':
            # should save the info received
            # callback with tuple (level, maxpeer, key range, ip)
            # be careful because python types are strange
            if data.startswith("JOIN_PRLY"):
                extra1,callback,level=self.extra
                temp=data.split()
                datum=(temp[2],temp[3],temp[4],self.remote)
                callback.joinatnormal(datum,level,1)
                protocol.sendMessage("JOIN_OKAY")
        elif self.mode=='join5':
            if data=="JOIN_OKAY":
                protocol.transport.loseConnection()
        elif self.mode=='join6':
            if data=="JOIN_OKAY":
                protocol.transport.loseConnection()
        elif self.mode=='exit1':
            protocol.transport.loseConnection()
        elif self.mode=='exit2':
            protocol.transport.loseConnection()
        elif self.mode=='exit3':
            if data.startswith("EXIT_PRLY"):
                callback=self.extra
                temp=data.split()
                datum=(temp[2],temp[3],temp[4],self.remote)
                callback.exitatbottom4(datum)
            protocol.transport.loseConnection()
        elif self.mode=='exit4':
            protocol.transport.loseConnection()
        elif self.mode=='exit5':
            protocol.transport.loseConnection()
        elif self.mode=='exit6':
            protocol.transport.loseConnection()
        elif self.mode=='exit7':
            protocol.transport.loseConnection()
        else:
            protocol.transport.loseConnection()
