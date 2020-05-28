#!/usr/bin/env python

import subprocess
import logging
import cherrypy
import atexit
import os

logging.basicConfig(filename='/tmp/dropcache.log', level=logging.DEBUG)
logger = logging.getLogger('dropcache')
logger.setLevel(logging.INFO)

def flush_log():
    logging.shutdown()

atexit.register(flush_log)

class DropKernelCache(object):

    @cherrypy.expose
    def index(self):
        return "Hi there\n"

    @cherrypy.expose
    def DropKernelCache(self):
        logger.info('asked for cache drop')
        try:
            os.sync()
            logger.info('completed sync call')
            with open('/proc_sys_vm/drop_caches','a') as dcf:
                dcf.write('3\n')
            logger.info('completed cache drop')
        except FileNotFoundError:
                logger.error('/proc_sys_vm/drop_caches not found')
        return 'SUCCESS'

if __name__ == '__main__':
    config = { 
        'global': {
            'server.socket_host': '0.0.0.0' ,
            'server.socket_port': 9435,
        },
    }
    cherrypy.config.update(config)
    cherrypy.quickstart(DropKernelCache())
