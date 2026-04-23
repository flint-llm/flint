import os
import json
import cloudpickle as pickle
import logging

from pipeline_monitor import prometheus_monitor as monitor
from pipeline_logger import log

_logger = logging.getLogger('model_logger')
_logger.setLevel(logging.INFO)
_logger_stream_handler = logging.StreamHandler()
_logger_stream_handler.setLevel(logging.INFO)
_logger.addHandler(_logger_stream_handler)

__all__ = ['predict']


_labels= {'model_runtime': os.environ['DATASPINE_MODEL_RUNTIME'],
          'model_type': os.environ['DATASPINE_MODEL_TYPE'],
          'model_name': os.environ['DATASPINE_MODEL_NAME'],
          'model_tag': os.environ['DATASPINE_MODEL_TAG']}


def _initialize_upon_import():
    model_pkl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.pkl')

    # Load pickled model from model directory
    with open(model_pkl_path, 'rb') as fh:
        restored_model = pickle.load(fh)

    return restored_model


# This is called unconditionally at *module import time*...
_model = _initialize_upon_import()


@log(labels=_labels, logger=_logger)
def predict(request: bytes) -> bytes:
    '''Where the magic happens...'''
    transformed_request = _transform_request(request)

    with monitor(labels=_labels, name="predict"):
        predictions = _predict(transformed_request)

    return _transform_response(predictions)


def _predict(inputs: dict) -> bytes:
#   _model.predict(...)    
    pass


@monitor(labels=_labels, name="transform_request")
def _transform_request(request):
#    request_str = request.decode('utf-8')
#    request_str = request_str.strip().replace('\n', ',')
#    request_dict = json.loads(request_str)
#    return request_dict
    pass

@monitor(labels=_labels, name="transform_response")
def _transform_response(response):
#    response_json = json.dumps(response)
#    return response_json
    pass
