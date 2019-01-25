#!/usr/bin/python3
import socket, ssl, sys, threading, re, json
from urllib.parse import urlparse
from datetime import datetime

# Single Serve Socket Server, recieve command and return result closing client socket
# multiple connections handled via threads

PORT = 9699 # the default port number to run our server on
HOST = socket.gethostname() # the default hostname to run on

CERTFILE = '/home/tpapad01/etc/server.pem'
# CERTFILE = None
LOGFILE = '/var/log/jServe.log'

__version__ = "0.0.1"


class jServe(threading.Thread):
    '''
        Process a json request from client, route to callback function, return json to client

        Args:
            callbacks (dict): Dictionary to use as callback registry *see add_callback()*
            port(int): Port number to use
            host(str): Hostname for server
            certfile(str): File to use for SSL *(if * **None** *SSL will not be used)*

        Attributes:
            output = 'json | xml' : default is json, type of output to return
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

        self.logger("jServ exit: received signal")

        self.server.close()
        sys.exit(signal)

    def logger (self, *msgs ):
        for msg in msgs:
            print (msg, file = self.logfile, end = '',flush = False )
            print (' ', file = self.logfile, end = '',flush = False )
        print ("", file = self.logfile, flush=True,  )


    def __init__(self, callbacks = {}, port=PORT , host=HOST, certfile = CERTFILE, logto = LOGFILE):
        import signal
        self.logto = logto
        self.logfile = open(self.logto, "a")
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
            self.logger('Not using SSL' )
        else:
            self.ssl = True
            self.logger('Certfile: ' + self.certfile )
        self.logger (datetime.now().strftime("jServe object initialized: %A %B %d %Y %I:%M %p %Z"))



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
            self.logger (datetime.now().strftime("jServe started: %A %B %d %Y %I:%M %p %Z"))
        except socket.error:
            self.logger('Bind failed %s' % (socket.error))
            sys.exit(1)


        self.server.listen(10)
        if self.ssl:
            self.logger (self.certfile)
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
            path(str),json(json), status(int), counter(int): Returns tupple with path, json object, status, and counter
        '''
        self.logger ("Callback not registered")

        return (path, {}, 404, counter + 1)


    def add_callback(self,method,path,cfunc):
        '''
        Register callback method, function should accept json object as data.

        Args:
            method (str): Method in URL POST, GET, PUT, etc..
            path (re): Path in URL after host '/.*', regular expression
            cfunc(function):  call back function refernce pointer (see default_callback() for details)


        Note user defined functions need to increment counter

        '''

        self.logger ("Call back add: ",method,path,cfunc)

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
                    if re.fullmatch(rep,path,re.I):
                        self.logger ("MATCH rep = {} path = {}".format(rep, path))
                        path, jdata, status, counter = m[rep](path,jdata,status=status, counter=counter)  #return first match for now

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
        self.logger('Client connected with ' + addr[0] + ':' + str(addr[1]))

        try:
            data = conn.recv(4096)
            self.logger ("data =",data)
        except Exception as err:
            data=""
            self.logger ("data = NULL")
        try:
            self.logger ('Parsing URL')
            url = urlparse(data)
        except:
            self.logger ('ERROR: Could not parse URL properly\nData =')
            self.logger (data)

            conn.close
            return False
        self.logger ("URL:",url)

        method, wpath, jdata = self.process_url (url)
        m1, rjdata, rcode, m2 = self.callback (method, wpath, jdata)
        self.logger ("%s:%s => %s %s %s" % ( addr[0],str(addr[1]),method, wpath, json.dumps(jdata)))

        conn.sendall(bytes(self.http_reply(json.dumps(rjdata),rcode),'utf-8'))
        self.logger ("closing connection from: "  + addr[0] + ':' + str(addr[1] ))

        conn.close() # Close
        return True

    def run(self):
        '''
        Opens connection, and creates Thread object to handle requests

        '''
        self.logger('Waiting for connections on port %s' % (self.port))

        # We need to run a loop and create a new thread for each connection
        while True:
          try:
              if self.ssl:
                  conn, addr = self.ssl.accept()
                  self.logger ("Using SSL connection")
              else:
                  self.logger ("Using Unsecure connection")
                  conn, addr = self.server.accept()
              threading.Thread(target=self.run_url_thread, args=(conn, addr)).start()
          except Exception as err:
            self.logger (err)


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
        resp += "Access-Control-Allow-Origin: *\n"  #Added to avoid CORS issue
        resp += "Content-Type: application/json; charset=utf-8\n"
        resp += "Connection: Closed\n\n"
        resp += data + "\n"
        self.logger ("Respone:")
        self.logger (resp)

        return resp


    def process_url (self,args):
        '''
        Break up URL string recieved in method, path, json

        Args:
            args(str): URL string

        Returns:
            method(str), path(str), json(json): tupple with data to be used for callbacks
        '''
        self.logger('process url')
        self.logger("ARGS =",args, args.path)

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
            return retstr

        urlst = args.path.decode('ascii').replace("["," [ ").replace("]"," ] ").replace("{"," { ").replace("}"," } ").replace(":"," : ").replace(","," , ").split()
        method = urlst[0]
        wpath = urlst[1]
        self.logger ("method = ", method, " wpath = ", wpath)

        if method == "GET":
            if args.query:
                params = args.query.decode('ascii').split()[0].replace("="," : ").replace("&"," , ")
                p = params.split(',')
                params = ''
                for i in p:
                    if ':' not in i:
                        i = i + ' : true '
                    params = params + i + ' , '
                params = params[:-3]
                params = params.split()

            else:
                params = []
        else:
            if args.query:
                ags = args.query
            else:
                ags = args.path
            try:
                urlst = ags.decode('ascii').replace("{"," { ").replace("}"," } ").replace(":"," : ").replace(","," , ").split()
                params = urlst[urlst.index("{")+1:urlst.index("}",-1)]
            except:
                params = []
        jstr = "{ " + join_escaped(params) + " }"
        self.logger (jstr)
        return (method,wpath, json.loads(jstr))

if __name__ == '__main__':
    ''' Below is an example and not called if imported as module '''
    def my_call (path, jdata, status=400, counter=0):
        jdata['more'] = 'testing'
        jdata['counter'] = counter
        return (path, jdata, status, counter + 1)

    myjs = jServe()
    myjs.add_callback("GET","/tes.*",my_call)
    myjs.add_callback("POST","/te.*",my_call)
    myjs.add_callback("POST","/t.*",my_call)
    myjs.add_callback("PUT","/t.*",my_call)
    myjs.start()
