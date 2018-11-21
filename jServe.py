#!/usr/bin/python3
import socket, ssl, sys, threading, re, json
from urllib.parse import urlparse, unquote_plus
from datetime import datetime
from dicttoxml import dicttoxml

# Single Serve Socket Server, recieve command and return result closing client socket
# multiple connections handled via threads

PORT = 9699 # the default port number to run our server on
HOST = socket.gethostname() #use default hostname to run on

# CERTFILE = '/home/TPapad01/work/etc/cert.pem'
CERTFILE = None
LOGFILE = '/var/log/jServe.log'

__version__ = "0.0.1"


class jServe(threading.Thread):
    '''
        Process a json request from client, route to callback function, return json (or XML) to client

        Parameters:
            callbacks (dict): Dictionary to use as callback registry *see add_callback()*
            port(int): Port number to use
            host(str): Hostname for server
            certfile(str): File to use for SSL *(if 'None' SSL will not be used)*

        Attributes
        ----------
                jServe.output = 'json' || 'xml' - default is json, controls type of output to return

        Methods
        -------------------------------------------------------------------------------
        '''


    def sig_exit(self,signal,fname):
        '''
        Receive signal to exit from OS

        Args:
            signal (signal): signal received
            fname (file): File name
        Returns:
            Exits program

        '''

        print ("jServ exit: received signal",signal,file = self.logfile)
        self.logfile.flush()
        self.server.close()
        sys.exit(signal)

    def __init__(self, callbacks = {}, port=PORT , host=HOST, certfile = CERTFILE, logfile = LOGFILE):
        import signal
        signal.signal(signal.SIGINT,self.sig_exit)
        threading.Thread.__init__(self)
        self.port = port
        self.output = 'json'  # 'xml' is also supported
        self.host = host
        self.certfile = certfile
        self.callregistry = callbacks
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if certfile is None:
            self.ssl = False
        else:
            self.ssl = True
        if logfile.upper() == "STDOUT":
            self.logfile = sys.stdout
        else:
            if logfile.upper() == "STDERR":
                self.logfile = sys.stderr
            else:
                self.logfile = open(LOGFILE, "a")

        print ("\n",file = self.logfile)
        print (datetime.now().strftime("jServe object initialized: %A %B %d %Y %I:%M %p %Z"),file = self.logfile)
        self.logfile.flush()


    def start (self):
        '''
        start() : will start the server, will not execute any other commands afterwards

        Args:
            None
        Returns:
            None

        '''
        try:
            self.server.bind((self.host, self.port))
            print (datetime.now().strftime("jServe started: %A %B %d %Y %I:%M %p %Z"),file = self.logfile)
        except socket.error:
            print('Bind failed %s' % (socket.error), file = self.logfile)
            sys.exit(1)

        self.logfile.flush()
        self.server.listen(10)
        if self.ssl:
            logger (self.certfile)
            self.ssl = ssl.wrap_socket(self.server, server_side = True, certfile=self.certfile, keyfile=self.certfile)
        self.run()

    def default_callback (self, path, jdata, status=400, counter=0):
        '''
        Call back to execute if one is not foundself.

        **Model callbacks on this function, counter should be incremented**

        Args:
            path (str): path in calling URL
            jdata (json): jquery data to process (required)
            status (int): last status
            counter (int): How many times method path did a call back

        Returns:
            path(str),json(json), status(int), counter(int)+1: Returns tupple with path, json object, status, and counter

        '''
        print ("Callback not registered",file = self.logfile)
        self.logfile.flush()
        return (path, {}, 404, counter + 1)


    def add_callback(self,method,path,cfunc):
        '''
        Register callback method, function should accept json object as data.

        Args:
            method (str): Method in URL POST, GET, PUT, etc..
            path (re): Path in URL after host '/.*', regular expression
            cfunc(function):  call back function refernce pointer (see default_callback() for details)

        Other:
            callback registry = {Method: [ {path : callback}, ]}

        Note:
            user defined functions need to increment counter inside callback set default_callback()

        '''

        print ("Call back add: ",method,path," callback: ",cfunc.__name__, file = self.logfile)
        self.logfile.flush()
        if method not in self.callregistry:
            self.callregistry[method] = []
        self.callregistry[method].append({path : cfunc })

    def callback (self, method, path, jdata):
        '''
        Find the callback based on method and path, the call it with jdata

        Args:
            method(str): Method from URL, used as primary key in callbacks
            path(str): path from URL
            jdata(json):

        '''
        status=200
        counter=0
        if method in self.callregistry:
            for m in self.callregistry[method]:
                for rep in m.keys():
                    # print ("rep = {} path = {}".format(rep, path), file = self.logfile)
                    if re.fullmatch(rep,path,re.I):
                        print ("MATCH rep = {} path = {}".format(rep, path), file = self.logfile)
                        path, jdata, status, counter = m[rep](path,jdata,status=status, counter=counter)  #return first match for now
                        self.logfile.flush()
            if counter != 0:
                return (path,jdata,status,counter)
        return self.default_callback(path,jdata,status,counter)

    def run_url_thread(self, conn, addr):
        '''
        Called from run(), process a single user request in a thread

        Args:
            conn(socket): came from accept()
            addr(list): TCPIP address Information
        Returns:
            sends response to Socket

        '''
        print('Client connected with ' + addr[0] + ':' + str(addr[1]),file = self.logfile)
        self.logfile.flush()
        try:
            data = conn.recv(4096)
        except Exception as err:
            data=""

        print ("RAW DATA:\n",data,"\n",file = self.logfile)
        method, wpath, jdata = self.process_url (data.decode('ascii'))
        m1, rjdata, rcode, m2 = self.callback (method, wpath, jdata)
        print ("%s:%s => %s %s %s" % ( addr[0],str(addr[1]),method, wpath, json.dumps(jdata)),file = self.logfile)
        self.logfile.flush()
        retdata = json.dumps(rjdata)
        if self.output == 'xml':
            retdata = dicttoxml(rjdata).decode()
        conn.sendall(bytes(self.http_reply(retdata,rcode),'utf-8'))
        print ("closing connection from: "  + addr[0] + ':' + str(addr[1] ), file = self.logfile)
        self.logfile.flush()
        conn.close() # Close

    def run(self):
        '''
        Opens connection, and creates Thread object to handle requests

        '''
        print('Waiting for connections on: %s port: %s' % (self.host,self.port),file = self.logfile)
        self.logfile.flush()
        # We need to run a loop and create a new thread for each connection
        while True:
          try:
              if self.ssl:
                  conn, addr = self.ssl.accept()
              else:
                  conn, addr = self.server.accept()
              threading.Thread(target=self.run_url_thread, args=(conn, addr)).start()
          except Exception as err:
            print (err, file = self.logfile)
        self.logfile.flush()

    def http_reply(self,data,status=200):
        '''
        Wraps json data in HTTP response

        Args:
            data (str): converted json string
            status(int): Status to return see stats table below
        Returns:
            HTTPD respnose string

        '''
        stats={  100 : "Continue", 101 : "Switching Protocols",
                 200 : "OK", 201 : "Created", 202 : "Accepted", 203 : "Non-Authoritative Information",
                 204 : "No Content", 205 : "Reset Content", 206 : "Partial Content",
                 300 : "Multiple Choices", 301 : "Moved Permanently", 302 : "Found",
                 303 : "See Other", 304 : "Not Modified", 307 : "Temporary Redirect", 308 : "Permanent Redirect",
                 400 : "Bad Request", 401 : "Unauthorized", 403 : "Forbidden", 404 : "Not Found",
                 405 : "Method Not Allowed", 406 : "Not Acceptable", 407 : "Proxy Authentication Required",
                 408 : "Request Timeout", 409 : "Conflict", 410 : "Gone", 411 : "Length Required",
                 412 : "Precondition Failed", 413 : "Payload Too Large", 414 : "URI Too Long",
                 415 : "Unsupported Media Type", 416 : "Range Not Satisfiable", 417 : "Expectation Failed",
                 418 : "I'm a teapot", 422 : "Unprocessable Entity", 426 : "Upgrade Required",
                 428 : "Precondition Required", 429 : "Too Many Requests",
                 431 : "Request Header Fields Too Large", 451 : "Unavailable For Legal Reasons",
                 500 : "Internal Server Error", 501 : "Not Implemented", 502 : "Bad Gateway",
                 503 : "Service Unavailable", 504 : "Gateway Timeout", 505 : "HTTP Version Not Supported",
                 511 : "Network Authentication Required" }

        resp = "HTTP/1.1 {} {}\n".format(status,stats[status])
        resp += "Date: {} GMT\n".format(datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S"))
        resp += "Server: jServ.py\n"
        resp += "Cache-Control: no-cache\n"
        resp += "Content-Length: {}\n".format(len(data))
        resp += "Content-Type: application/json; charset=utf-8\n"
        resp += "Connection: Closed\n\n"
        resp += data + "\n"
        print ("Respone:\n",resp,file=self.logfile)
        self.logfile.flush()
        return resp

    def __process_path(self,data):
        try:
            pstr = re.search('.*({.*}).*',data).group(1)
        except:
            return "{}"
        print ("PATH PARAMS = ",pstr, file = self.logfile)
        return pstr

    def __process_query(self,data):
        # qparams = args.query.decode('ascii').split()[0].replace("="," : ").replace("&"," , ")
        qry = data.split()[1]
        if '?' in qry:
            qry = qry.split('?')[1]
        if '&' in qry:
            qparams = qry.split()[0].split('&')
            qstr = "{"
            sep = ""
            for i in qparams:
                p = i.split("=")
                qstr = qstr + sep + '"' + p[0] + '" : '
                if len(p) > 1:
                    qstr = qstr + '"' + unquote_plus(p[1]) + '"'
                sep = ", "
            qstr = qstr + "}"
        else:
            qstr = "{}"
        print ("GET PARAMS = ",qstr, file = self.logfile)
        return qstr


    def process_url (self,data):
        #URL = data.decode('ascii')
        method = data.split()[0]
        wpath = data.split()[1]
        if '&' in wpath:
            wpath = wpath.split('&')[0]
        jstr = {}
        jstr.update(json.loads(self.__process_path(data)))
        jstr.update(json.loads(self.__process_query(data)))
        print  (method,wpath, jstr, file = self.logfile)
        return (method,wpath, jstr)

    def process_url_old (self,args):
        '''
        Break up URL string recieved in method, path, json

        Args:
            args(str): URL string

        Returns:
            method(str), path(str), json(json): tupple with data to be used for callbacks
        '''
        def is_number(j):
            try:
                if float(j):
                    return True
            except:
                return False

        def join_escaped(lst,sep='"'):
            retstr = ""
            tbl = str.maketrans({sep: chr(92)+sep})
            for i in lst:
                k = i
                if (k[0] == '"' and k[-1] == '"') or (k[0] == "'" and k[-1] == "'") or (k[0] == sep and k[-1] == sep) :
                    k = k[1:-1]
                    k = k.translate(tbl)
                if i == ':' or i == ',' or i == '}' or i == '{' or i == "[" or i == "]" or is_number(i) or i == 'true':
                    j = k
                else:
                    j = sep + k + sep
                retstr =  retstr + " " + j
            retstr = re.sub('%20',' ',retstr)
            return retstr

        def retDefined(p1,p2,p3):
            print (p1,p2,p3)
            pr = p1
            if len(pr) == 0:
                pr = p2
            if len(pr) == 0:
                pr = p3
            return pr

        print ("URL = ", args, file = self.logfile)
        urlst = args.path.decode('ascii').strip().replace("["," [ ").replace("]"," ] ").replace("{"," { ").replace("}"," } ").replace(":"," : ").replace(","," , ").split()
        method = urlst[0]
        wpath = urlst[1]
        print ("method = ", method, " wpath = ", wpath, file = self.logfile)
        self.logfile.flush()
        qparams = []
        if args.query:
            qparams = args.query.decode('ascii').split()[0].replace("="," : ").replace("&"," , ")
            p = qparams.split(',')
            qparams = ''
            for i in p:
                if ':' not in i:
                    i = i + ' : true '
                qparams = qparams + i + ' , '
            qparams = qparams[:-3]
            # print (params, file = self.logfile)
            qparams = qparams.split()
        prparams = []
        if args.params:
            if "form-data;" in args.params.decode('ascii'):
                urlst = re.sub(' +',' ',args.params.decode('ascii').replace("\r"," ").replace("\n"," ")[1:])
                urlst = urlst.split("form-data; ")
                for i in urlst:
                    if 'name=' not in i:
                        urlst.remove(i)
                print (urlst)
                for i in range(0,len(urlst)):
                    urlst[i] = re.sub('\-\-\-.*','',urlst[i]).strip().replace('name="','').replace('"',':')
                    u = urlst[i].split(":")
                    print (u)
                    u[1] = re.sub(' ','%20',u[1].strip())
                    urlst[i] = ' : '.join(u)
                    print (u)
                prparams = ' , '.join(urlst).split()
                print (prparams)
        ptparams = []
        if args.path:
            #try:
            print (args.path)
            #urlst = args.path.decode('ascii').replace("{"," { ").replace("}"," } ").replace(":"," : ").replace(","," , ").split()
            urlst = re.sub("^.*?{","",args.path.decode('ascii'))
            urlst = re.sub('}$','',urlst).replace('",','" ,"')
            u1 = urlst.split(" , ")
            for i in range(0,len(u1)):
                u2 = u1[i].split(":")
                u2[1] = re.sub(" ","%20",u2[1])
                u1[i] = ':'.join(u2)
            urlst = ','.join(u1)
            print (urlst)
            #ptparams = urlst[urlst.index("{")+1:urlst.index("}",-1)]
            ptparams = urlst.split(',')
            print (ptparams)
            #except:
            #   pass

        if method in ["GET","DELETE"]:
            params = retDefined ( qparams, ptparams, prparams)
        if method in ["POST","PUT"]:
            params = retDefined (ptparams, prparams, qparams )

        jstr = "{ " + join_escaped(params) + " }"
        print (jstr,file = self.logfile)
        self.logfile.flush()
        return (method,wpath, json.loads(jstr))

if __name__ == '__main__':
    ''' Below is an example and not called if imported as module '''
    def my_call (path, jdata, status=400, counter=0):
        # print ("my_call: \n\t===>>> ",jdata)
        jdata['more'] = 'testing'
        jdata['counter'] = counter
        # print ("\n\t\t===>>> ",jdata)
        return (path, jdata, status, counter + 1)

    myjs = jServe(logfile="stderr")
    # myjs.output = 'xml'
    myjs.add_callback("GET","/tes.*",my_call)
    myjs.add_callback("POST","/te.*",my_call)
    myjs.add_callback("POST","/t.*",my_call)
    myjs.add_callback("PUT","/t.*",my_call)
    # print (myjs.callregistry)
    myjs.start()
