from flask import request, url_for
from flask_api import FlaskAPI, status, exceptions
from .cli_dataspine import version
from .training import DataspineCli

app = FlaskAPI(__name__)

notes = {
    0: 'do the shopping',
    1: 'build the codez',
    2: 'paint the door',
}

def note_repr(key):
    return {
        'url': request.host_url.rstrip('/') + url_for('notes_detail', key=key),
        'text': notes[key]
    }


@app.route("/", methods=['GET'])
def version():
    return {"version": version}

@app.route("/notes", methods=['GET', 'POST'])
def notes_list():
    """
    List or create notes.
    """
    return {'version': version}

#    if request.method == 'POST':
#        note = str(request.data.get('text', ''))
#        idx = max(notes.keys()) + 1
#        notes[idx] = note
#        return note_repr(idx), status.HTTP_201_CREATED

    # request.method == 'GET'
#    return [note_repr(idx) for idx in sorted(notes.keys())]

_dataspine = DataspineCli()

@app.route("/predict-kafka-describe/<string:model_name>/", methods=['GET'])
def predict_kafka_describe(model_name):
    return _dataspine.predict_kafka_describe(model_name=model_name)

#@app.route("/note/<int:key>/", methods=['GET', 'PUT', 'DELETE'])
@app.route("/predict-server-test/<string:model_name>/", methods=['POST'])
def predict_server_test(model_name):
    """
    Retrieve, update or delete note instances.
    """
    if request.method == 'POST':
        test_request_body = str(request.data.get('text', ''))
        model_endpoint_url = ""
        return _dataspine.predict_server_test(model_endpoint_url, test_request_body)

        #notes[key] = note
        #return note_repr(key)
#    elif request.method == 'DELETE':
#        notes.pop(key, None)
#        return '', status.HTTP_204_NO_CONTENT

#    # request.method == 'GET'
#    if key not in notes:
#        raise exceptions.NotFound()
#    return note_repr(key)


@app.route("/predict-kube-list/", methods=['GET'])
def predict_kube_list():
    import glob

    filename = 'dataspine_status'

    for filename in glob.glob('./*'):
        with open(filename, 'r') as fh:
            print(fh.read())


if __name__ == "__main__":
    app.run(debug=True)
