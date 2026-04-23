import os
import numpy as np
import json
import logging
import cloudpickle as pickle

from pipeline_model import TensorFlowServingModel
from pipeline_monitor import prometheus_monitor as monitor
from pipeline_logger import log

_logger = logging.getLogger('pipeline-logger')
_logger.setLevel(logging.INFO)
_logger_stream_handler = logging.StreamHandler()
_logger_stream_handler.setLevel(logging.INFO)
_logger.addHandler(_logger_stream_handler)


__all__ = ['predict']


_labels= {'model_runtime': '{{ DATASPINE_MODEL_RUNTIME}}',
          'model_type': '{{ DATASPINE_MODEL_TYPE }}',
          'model_name': '{{ DATASPINE_MODEL_NAME }}',
          'model_tag': '{{ DATASPINE_MODEL_TAG }}',
          'model_chip': '{{ DATASPINE_MODEL_CHIP }}',
         }


def _initialize_upon_import():
    ''' Initialize / Restore Model Object.
    '''
    # TODO: Unpickle a model
    pass

# This is called unconditionally at *module import time*...
_model = _initialize_upon_import()


@log(labels=_labels, logger=_logger)
def predict(request: bytes) -> bytes:
    '''Where the magic happens...'''

    with monitor(labels=_labels, name="transform_request"):
        transformed_request = _transform_request(request)

    with monitor(labels=_labels, name="predict"):
        predictions = _model.predict(transformed_request)

    with monitor(labels=_labels, name="transform_response"):
        transformed_response = _transform_response(predictions)

    return transformed_response


def _transform_request(request: bytes) -> dict:
    # Convert from bytes to tf.tensor, np.array, etc.
    pass


def _transform_response(response: dict) -> json:
    # Convert from tf.tensor, np.array, etc. to bytes
    pass
