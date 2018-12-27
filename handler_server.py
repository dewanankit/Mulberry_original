from twisted.internet.protocol import Protocol
from twisted.internet.protocol import Factory
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet import reactor
from random import randrange
from sys import stdout

from handler_client import ClientHandler
from data_state import Conn

## comment preceded by '##' is concerned with over structure of code
# comment preceded by '#' is concerned with a specific segment's purpose

class MulSvr(Protocol):
    # instance variables:
    # factory: (factory object)
    # connum: (counter that increment for every message)
    # transport: (object used to send messages)

    def __init__(self, factory, connum):
        self.factory = factory
        self.connum = connum

    def connectionMade(self):
        stdout.write("connection %d made.\n" % self.connum)

    def connectionLost(self, reason):
        stdout.write("connection %d finished.\n" % self.connum)

    def dataReceived(self, data):
        stdout.write("connection %d received data.\n" % self.connum)
        for datum in data.split(";"):
            if datum is None or datum=="":
                continue
            self.factory.serverhandler.processRequest(self, datum)

    def sendMessage(self, data):
        stdout.write("connection %d sent data.\n" % self.connum)
        self.transport.write(data+";")

class MulSvrFactory(Factory):
    # instance variables
    # number: i don't know what this does
    # serverhandler: the server handler, has all the callback methods

    def __init__(self, serverhandler):
        self.number=0
        self.serverhandler=serverhandler

    def buildProtocol(self, addr):
        newsvr = MulSvr(self, self.number)
        self.number = self.number + 1
        return newsvr

class ServerHandler:
    # instance variable
    # state: the state object is used to maintain state of my network view

    def __init__(self,state):
        self.state=state
        self.joinatnormal_stagep=0
        # max number is non inclusive and min number is inclusive
        self.maxnumberofpeeratlastlevel=8
        self.minnumberofpeeratlastlevel=2

    ## code must be used to make twisted work
    def startup(self):
        endpoint = TCP4ServerEndpoint(reactor, self.state.myconn.port)
        endpoint.listen(MulSvrFactory(self))

    ## the main callback method to process everything
    def processRequest(self, protocol, data):
        ## reply a greeting, to test out connection
        if data=="HELLO":
            protocol.sendMessage("HELLO")
        elif data.startswith("JOIN_INIT"):
            protocol.sendMessage("WAIT")
            self.join(protocol,data.split(),0)
        elif data.startswith("JOIN_OKAY"):
            protocol.transport.loseConnection()
        ## this was sent by a peer multicasting about a new peer joining last level
        elif data.startswith("JOIN_BOTT"):
            # seperate out argument passed in and construct a connection object
            parameters=data.split()
            joinerip=parameters[2]
            joinerport=int(parameters[3])
            joinername=parameters[4]
            joinerconn=Conn(joinerip,joinerport,joinername)
            # add the connection to my last level
            self.state.lastlevel.append(joinerconn)
            protocol.sendMessage("JOIN_OKAY")
            self.checksplit()
            self.state.printinfo()
        ## this was sent to new peer, receives a list of peers to add to one level
        elif data.startswith("JOIN_LIST"):
            partialparam=data.split("\n")
            leveloflist=int((partialparam[0].split())[2])
            numberofpeer=int((partialparam[0].split())[3])
            # construct new peer list of that level, note order is important
            newlist=[]
            for i in range(0,numberofpeer):
                parameters=partialparam[1+i].split()
                contactip=parameters[0]
                contactport=int(parameters[1])
                contactname=parameters[2]
                newconn=Conn(contactip,contactport,contactname)
                newlist.append(newconn)
            if leveloflist==len(self.state.conns):
                self.state.addlevel(newlist)
            else:
                stdout.write("joinlist:\twhere am I getting the list from?\n")
            protocol.sendMessage("JOIN_OKAY")
            self.state.printinfo()
        ## this was sent to peers at a none last level, polling its states
        elif data.startswith("JOIN_POLL"):
            # response with level, max peer, key range
            #replymsg="JOIN_PRLY "+self.state.myconn.name+" "+str(self.state.curmaxlv)+" "+str(len(self.state.conns[self.state.curmaxlv]))+" "+str('123')
            replymsg="JOIN_PRLY "+self.state.myconn.name+" "+str(len(self.state.conns))+" "+str(len(self.state.lastlevel))+" "+str('123')
            protocol.sendMessage(replymsg)
        ## forwarded the join request to me
        elif data.startswith("JOIN_FRWD"):
            protocol.sendMessage("JOIN_OKAY")
            # remember [a:b] takes a to b-1, b is not included
            self.join(protocol,data.split()[:5],int(data.split()[5]))
        ## this was sent to new peer, receives a list of peers to add to last level
        elif data.startswith("JOIN_LAST"):
            partialparam=data.split("\n")
            numberofpeer=int((partialparam[0].split())[2])
            newlist=[]
            for i in range(0,numberofpeer):
                parameters=partialparam[1+i].split()
                contactip=parameters[0]
                contactport=int(parameters[1])
                contactname=parameters[2]
                newconn=Conn(contactip,contactport,contactname)
                newlist.append(newconn)
            self.state.lastlevel=newlist
            protocol.sendMessage("JOIN_OKAY")
            self.checksplit()
            self.state.printinfo()
        elif data.startswith("EXIT_INIT"):
            parameters=data.split()
            exiteraddr=parameters[2]
            exiterport=int(parameters[3])
            exitername=parameters[4]
            exiterlevel=int(parameters[5])
            exiterconn=Conn(exiteraddr,exiterport,exitername)
            if exiterlevel==len(self.state.conns):
                # exiting at last level
                self.exitatbottom(exiterconn)
            # do nothing if not at last level
            self.state.printinfo()
        elif data.startswith("EXIT_ELCT"):
            # receive a election request
            self.exitatbottom2()
        elif data.startswith("EXIT_POLL"):
            # response with number level, number of peers at last level, key range
            replymsg="EXIT_PRLY "+self.state.myconn.name+" "+str(len(self.state.conns))+" "+str(len(self.state.lastlevel))+" "+str('123')
            protocol.sendMessage(replymsg)
        elif data.startswith("EXIT_FRWD"):
            # receive request for peer transfer
            parameters=data.split()
            exiteraddr=parameters[2]
            exiterport=int(parameters[3])
            exitername=parameters[4]
            exiterlevel=int(parameters[5])
            exiterpos=int(parameters[6])
            exiterconn=Conn(exiteraddr,exiterport,exitername)
            self.exitatbottom6(exiterconn,exiterlevel,exiterpos)
        elif data.startswith("EXIT_JOIN"):
            parameters=data.split()
            joineraddr=parameters[2]
            joinerport=int(parameters[3])
            joinername=parameters[4]
            joinerconn=Conn(joineraddr,joinerport,joinername)
            self.exitatbottom7(joinerconn)
        elif data.startswith("EXIT_BRCT"):
            parameters=data.split()
            joineraddr=parameters[2]
            joinerport=int(parameters[3])
            joinername=parameters[4]
            joinerconn=Conn(joineraddr,joinerport,joinername)
            self.exitatbottom8(joinerconn)
            self.state.printinfo()
        elif data.startswith("EXIT_LIST"):
            partialparam=data.split("\n")
            numberofpeer=int((partialparam[0].split())[2])
            newlist=[]
            for i in range(0,numberofpeer):
                parameters=partialparam[1+i].split()
                contactaddr=parameters[0]
                contactport=int(parameters[1])
                contactname=parameters[2]
                newconn=Conn(contactaddr,contactport,contactname)
                newlist.append(newconn)
            self.exitatbottom9(newlist)
            self.state.printinfo()
        else:
            protocol.sendMessage("NO SUPPORT")

    #def join(self,protocol,parameters,level):
    def join(self,protocol,parameters,level):
        if level<len(self.state.conns):
            # just join
            # contact peers and poll
            # select winner
            # replace winner with new comer, and send list to comer
            # forward request for winner to handle
            self.joinatnormal(parameters,level,0)
        elif level==len(self.state.conns):
            self.joinatbottom(parameters)
            #self.checksplit()
        self.state.printinfo()

    # a join at any level other than last level
    def joinatnormal(self,parameters,level,stage):
        # static method variable
        # self.joinatnormal_stagep: stage of the operation, 3 total
        # self.joinatnormal_responses: the list of responses from poll
        # self.joinatnormal_joinerconn: joiner's information
        if stage==0 and self.joinatnormal_stagep==0:
            # send everyone a poll message
            self.joinatnormal_stagep=1
            self.joinatnormal_responses=[]
            joinerip=parameters[2]
            joinerport=int(parameters[3])
            joinername=parameters[4]
            joinerconn=Conn(joinerip,joinerport,joinername)
            self.joinatnormal_joinerconn=joinerconn
            for peer in self.state.conns[level]:
                ClientHandler(self.state,peer,'join4',(joinerconn,self,level)).startup()
            #reactor.callLater(5,self.joinatnormal,parameters,level,2)
        elif stage==1 and self.joinatnormal_stagep==1:
            # receive responses until timeout or we have everyone's response
            # parameters is tuple level, maxpeer, key range, ip
            self.joinatnormal_responses.append(parameters)
            if len(self.joinatnormal_responses)==len(self.state.conns[level]):
                #reactor.callLater(1,self.joinatnormal,None,level,2)
                self.joinatnormal(None,level,2)
        elif stage==2 and self.joinatnormal_stagep==1:
            # clearly indicate we have timed out and can no more receive connections
            self.joinatnormal_stagep=0
            joinerconn=self.joinatnormal_joinerconn
            self.joinatnormal_responses.sort()
            # now we have the winner first send joiner a list then forward request
            # peerlist must have your own ip as well, replace winner by joiner
            newpeerlist=self.state.conns[level][:] # shallow copy the list
            winner=(filter(lambda x:(x.addr==self.joinatnormal_responses[0][3].addr and
                    x.port==self.joinatnormal_responses[0][3].port),newpeerlist))[0]
            try:
                newpeerlist[newpeerlist.index(winner)]=joinerconn
            except ValueError:
                pass
            ClientHandler(self.state,joinerconn,'join3',(newpeerlist,level)).startup()
            # forward request to the winner at next level
            ClientHandler(self.state,winner,'join5',(joinerconn,level+1)).startup()
            # there is a probability of winner being replaced by this new guy
            if winner.addr!=self.state.myconn.addr and winner.port!= self.state.myconn.port:
                if randrange(0,100)<10:
                    try:
                        mylist=self.state.conns[level]
                        #self.state.conns[level].remove(winner)
                        #self.state.conns[level].append(joinerconn)
                        mylist[mylist.index(winner)]=joinerconn
                    except ValueError:
                        pass

    def joinatbottom(self,parameters):
        # lock
        # send messages to all the peers in the group
        # and then send client a contact list
        # check split
        joinerip=parameters[2]
        joinerport=int(parameters[3])
        joinername=parameters[4]
        joinerconn=Conn(joinerip,joinerport,joinername)
        lastlevel=self.state.lastlevel[:]
        for peer in self.state.lastlevel:
            ClientHandler(self.state,peer,'join2',joinerconn).startup()
            #ClientHandler(self.state,peer,'join2',Conn(joinerip,joinerport,joinername)).startup()
        lastlevel.append(joinerconn)
        ClientHandler(self.state,joinerconn,'join6',(lastlevel)).startup()
        # don't need to append because I will send myself a message
        #self.state.conns[level].append(Conn(joinerip,joinerport,joinername))

    # new checksplit
    def checksplit(self):
        self.state.chkstate()
        maxnumberofpeeratlastlevel=self.maxnumberofpeeratlastlevel
        if len(self.state.lastlevel)==maxnumberofpeeratlastlevel:
            # first split by finding mygroup and copying mygroup
            myconn=self.state.myconn
            newlist=self.state.lastlevel[:]
            newlist.sort(key=lambda x:(x.addr,x.port))
            indexofconn=newlist.index(myconn)
            mygroup=indexofconn*4/maxnumberofpeeratlastlevel
            stdout.write("checksplit: my group "+str(mygroup)+"\n")
            self.state.lastlevel=newlist[mygroup*maxnumberofpeeratlastlevel/4:(mygroup+1)*maxnumberofpeeratlastlevel/4]
            # then get the last-1 peers and do something
            # list is supposed to be myself and random peers from each group
            list=[None]*4
            for x in range(0,4):
                if x==mygroup:
                    myconn=self.state.myconn
                    list[x]=myconn
                else:
                    list[x]=newlist[x*maxnumberofpeeratlastlevel/4+randrange(0,maxnumberofpeeratlastlevel/4)]
                #stdout.write("checksplit: group "+str(x)+"\n")
            # last update last-1 given list
            self.updatelast(list)
        self.state.chkstate()
        return

    # update last-1 level
    def updatelast(self,list):
        # first update last-1
        if len(list)!=4:
            sys.stdout.write("checksplit: list not 4\n")
        self.state.addlevel(list)
        stdout.write("checksplit: level added\n")
        return

    def exitinit(self):
        ## tell people you are leaving, mainly for people in your last level
        # because in other levels your peer's peer may not be you
        myconn=self.state.myconn
        newlist=self.state.lastlevel[:]
        newlist.sort(key=lambda x:(x.addr,x.port))
        newlist.remove(myconn)
        for peer in newlist:
            ClientHandler(self.state,peer,'exit1',len(self.state.conns)).startup()
        return

    def exitatnormal(self):
        # received exit node not at bottom level
        return

    def exitatbottom(self,exiterconn):
        ## some node is unreachable at the last level
        # sends a election message, that ask everybody to do the same thing
        self.state.lastlevel.remove(exiterconn)
        minnumberofpeeratlastlevel=self.minnumberofpeeratlastlevel
        if len(self.state.lastlevel)<minnumberofpeeratlastlevel:
            for peer in self.state.lastlevel:
                ClientHandler(self.state,peer,'exit2',None).startup()
        return

    def exitatbottom2(self):
        ## gets called when we have an election message
        ## decide if we are the winner
        myconn=self.state.myconn
        newlist=self.state.lastlevel[:]
        newlist.sort(key=lambda x:(x.addr,x.port))
        indexofconn=newlist.index(myconn)
        if indexofconn==0:
            self.exitatbottom3()

    def exitatbottom3(self):
        # we won if we are the first person
        # poll my peers at level above last, see who has most levels
        self.exitatbottom_resultlist=[]
        for peer in self.state.conns[len(self.state.conns)-1]:
            ClientHandler(self.state,peer,'exit3',self).startup()

    def exitatbottom4(self,result):
        ## gets responses from the poll and add it to a list
        resultlist=self.exitatbottom_resultlist
        levelabovelast=self.state.conns[len(self.state.conns)-1]
        resultlist.append(result)
        if len(resultlist)==len(levelabovelast):
            self.exitatbottom5()

    def exitatbottom5(self):
        ## after the poll, find a winner, send the request, or do a shrink
        minnumberofpeeratlastlevel=self.minnumberofpeeratlastlevel
        resultlist=self.exitatbottom_resultlist
        levelabovelast=self.state.conns[len(self.state.conns)-1]
        ############
        resultlist.sort(key=lambda r:(r[0],r[1],r[2]),reverse=True)
        stdout.write("exitbot: "+resultlist[0][3].name+"\n")
        if resultlist[0][0]==len(self.state.conns) and resultlist[0][1]==minnumberofpeeratlastlevel:
            ## do a shrink
            self.shrinking()
        else:
            ## ask for a peer trasfer
            # send the winner a message with my info so i wait for contact
            winnerconn=resultlist[0][3]
            # if you do recursion, it is not always me that wants to exit
            exiterpos=levelabovelast.index(self.state.myconn)
            ClientHandler(self.state,winnerconn,'exit4',(self.state.myconn,len(self.state.conns),exiterpos)).startup()

    def exitatbottom6(self,exiterconn,exiterlevel,exiterpos):
        ## receive the peer transfer request, if we are at last level, then transfer
        ## if we are not at last level, we forward to level below
        if exiterlevel==len(self.state.conns):
            # send exit
            self.exitinit()
            # change level above last
            levelabovelast=self.state.conns[len(self.state.conns)-1]
            lastlevel=self.state.lastlevel
            myconn=self.state.myconn
            indexofmyconn=levelabovelast.index(myconn)
            levelabovelast[exiterpos]=myconn
            lastlevel.remove(myconn)
            levelabovelast[indexofmyconn]=lastlevel[randrange(0,len(lastlevel))]
            # then transfer myself
            ClientHandler(self.state,exiterconn,'exit5',self.state.myconn).startup()
        else:
            # send transfer request to next level
            self.exitatbottom3()

    def exitatbottom7(self,joinerconn):
        ## on receiving transfer reply, broadcast it to group
        lastlevel=self.state.lastlevel[:]
        for peer in self.state.lastlevel:
            ClientHandler(self.state,peer,'exit6',joinerconn).startup()
        # send a list of peers to the new peer
        lastlevel.append(joinerconn)
        ClientHandler(self.state,joinerconn,'exit7',lastlevel).startup()

    def exitatbottom8(self,joinerconn):
        ## receive new peer
        self.state.lastlevel.append(joinerconn)

    def exitatbottom9(self,bottomlist):
        ## receive peer list
        # replace last level
        stdout.write("exitbot: got peer list\n")
        self.state.lastlevel=bottomlist

    def shrinking(self):
        ## starting a shrink
        ## broadcast a lockdown
        stdout.write("shrink not yet implemented!\n")

    def shrinking2(self):
        ## after peer confirm lockdown, send info to ring leaders
        stdout.write("shrink not yet implemented!\n")

    def shrinking3(self):
        ## after getting all info, send it to peer
        stdout.write("shrink not yet implemented!\n")

    def shrinking4(self):
        ## unlock
        stdout.write("shrink not yet implemented!\n")
