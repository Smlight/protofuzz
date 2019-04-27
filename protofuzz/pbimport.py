#!/usr/bin/env python3

'''
Collection of functions dealing with locating and using the protobuf compiler.
'''

import sys
import os
import tempfile
import subprocess
import re
import importlib
import importlib.util
import importlib.machinery

__all__ = ['BadProtobuf', 'ProtocNotFound', 'from_string', 'from_file',
           'types_from_module']


class BadProtobuf(Exception):
    '''
    Raised when .proto file has errors'
    '''
    pass


class ProtocNotFound(Exception):
    '''
    Raised when failing to find the protoc binary
    '''
    pass


def find_protoc(path=os.environ['PATH']):
    '''
    Traverse a path ($PATH by default) to find the protoc compiler
    '''
    protoc_filename = 'protoc'

    bin_search_paths = path.split(':') or []
    for search_path in bin_search_paths:
        bin_path = os.path.join(search_path, protoc_filename)
        if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
            return bin_path

    raise ProtocNotFound("Protobuf compiler not found")


def from_string(proto_str):
    '''
    Produce a Protobuf module from a string description.

    Return the module if successfully compiled, otherwise raise a BadProtobuf
    exception.
    '''
    _, proto_file = tempfile.mkstemp(suffix='.proto')

    with open(proto_file, 'w+') as proto_f:
        proto_f.write(proto_str)

    return from_file(proto_file)


def _load_module(path):
    'Helper to load a Python file at path and return as a module'

    print(os.path.abspath('.'))
    module_name = os.path.splitext(os.path.basename(path))[0]
    module = None
    
    if sys.version_info.minor < 5:
        loader = importlib.machinery.SourceFileLoader(module_name, path)
        module = loader.load_module()
    else:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    return module


def _compile_proto(full_path, dest):
    'Helper to compile protobuf files'
    proto_path = os.path.dirname(full_path)
    working_path = os.path.abspath('.')
    protoc_args = [find_protoc(),
                   '--python_out={}'.format(dest),
                   '--proto_path={}'.format(working_path),
                   full_path]
    proc = subprocess.Popen(protoc_args, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        outs, errs = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        outs, errs = proc.communicate()
        return False

    if proc.returncode != 0:
        msg = 'Failed compiling "{}": \n\nstderr: {}\nstdout: {}'.format(
            full_path, errs.decode('utf-8'), outs.decode('utf-8'))
        raise BadProtobuf(msg)

    return True


def from_file(proto_file, dest=None):
    '''
    Take a filename |protoc_file|, compile it via the Protobuf
    compiler, and import the module.

    Return the module if successfully compiled, otherwise raise either
    a ProtocNotFound or BadProtobuf exception.
    '''
    
    if not proto_file.endswith('.proto'):
        raise BadProtobuf()

    first = False
    if not dest:
        dest = tempfile.mkdtemp()
        first = True
        print(dest)

    print(proto_file)
    
    full_path = os.path.abspath(proto_file)
    working_path = os.path.abspath('.')
    _compile_proto(full_path, dest)

    filename = os.path.split(full_path)[-1]
    name = re.search(r'^(.*)\.proto$', filename).group(1)
    
    target = os.path.join(dest, proto_file[:-6]+'_pb2.py')
    with open(proto_file) as fpro:
        for line in fpro:
            tmp = re.search(r'import\s*"(.*\.proto)"', line)
            if tmp:
                subproto = tmp.group(1)
                from_file(subproto, dest)
    
    if first:
        os.chdir(dest)
        return _load_module(proto_file[:-6]+'_pb2.py')


def types_from_module(pb_module):
    '''
    Return protobuf class types from an imported generated module.
    '''
    types = pb_module.DESCRIPTOR.message_types_by_name
    return [getattr(pb_module, name) for name in types]
