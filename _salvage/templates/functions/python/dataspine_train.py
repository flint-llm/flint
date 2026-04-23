import cloudpickle as pickle

if __name__ == '__main__':

    model = {}

    model_pkl_path = 'model.pkl'

    with open(model_pkl_path, 'wb') as fh:
        pickle.dump(model, fh)
