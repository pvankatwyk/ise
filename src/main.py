from data.processing.aggregate_by_sector import aggregate_atmosphere, aggregate_icecollapse, aggregate_ocean
from data.processing.process_outputs import process_repository
from data.processing.combine_datasets import combine_datasets
from data.classes.EmulatorData import EmulatorData
from training.Trainer import Trainer
from models import ExploratoryModel, TimeSeriesEmulator
from utils import get_configs, output_test_series, plot_true_vs_predicted
from sklearn.metrics import r2_score
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import numpy as np
import random
from datetime import datetime

cfg = get_configs()
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
np.random.seed(10)

forcing_directory = cfg['data']['forcing']
zenodo_directory = cfg['data']['output']
export_dir = cfg['data']['export']
processing = cfg['processing']
data_directory = cfg['data']['directory']

if processing['generate_atmospheric_forcing']:
    af_directory = f"{forcing_directory}/Atmosphere_Forcing/"
    aggregate_atmosphere(af_directory, export=export_dir, )

if processing['generate_oceanic_forcing']:
    of_directory = f"{forcing_directory}/Ocean_Forcing/"
    aggregate_ocean(of_directory, export=export_dir, )

if processing['generate_icecollapse_forcing']:
    ice_directory = f"{forcing_directory}/Ice_Shelf_Fracture"
    aggregate_icecollapse(ice_directory, export=export_dir, )

if processing['generate_outputs']:
    outputs = process_repository(zenodo_directory, export_filepath=f"{export_dir}/outputs.csv")

if processing['combine_datasets']:
    master, inputs, outputs = combine_datasets(processed_data_dir=export_dir,
                                               include_icecollapse=processing['include_icecollapse'],
                                               export=export_dir)


def test_saved_network(path, architecture):
    print('1/3: Loading in Data')
    emulator_data = EmulatorData(directory=export_dir)
    print('2/3: Processing Data')
    emulator_data, train_features, test_features, train_labels, test_labels = emulator_data.process(
        target_column='sle',
        drop_missing=True,
        drop_columns=['groupname', 'experiment'],
        boolean_indices=True,
        scale=True,
        split_type='batch_test',
        drop_outliers={'column': 'ivaf', 'operator': '<', 'value': -1e13},
        time_series=True,
        lag=5,
    )
    data_dict = {'train_features': train_features,
                'train_labels': train_labels,
                'test_features': test_features,
                'test_labels': test_labels, }
    
    # Load Model
    trainer = Trainer(cfg)
    trainer._initiate_model(TimeSeriesEmulator.TimeSeriesEmulator, data_dict=data_dict, architecture=architecture, sequence_length=5, batch_size=100)
    
    # Assigned pre-trained weights
    trainer.model.load_state_dict(torch.load(path, map_location=device))
    model = trainer.model
    
    # Evaluate on test_features
    print('3/3: Evaluating')
    model.eval()
    X_test = torch.from_numpy(np.array(test_features, dtype=np.float64)).float()
    preds = model.predict(X_test)
    
    mse = sum((preds - test_labels)**2) / len(preds)
    mae = sum((preds - test_labels)) / len(preds)
    rmse = np.sqrt(mse)
    r2 = r2_score(test_labels, preds)
    
    metrics = {'MSE': mse, 'MAE': mae, 'RMSE': rmse, 'R2': r2}

    print(f"""Test Metrics
MSE: {mse:0.6f}
MAE: {mae:0.6f}
RMSE: {rmse:0.6f}
R2: {r2:0.6f}""")

    return metrics, preds
    


def run_network():
    print('1/4: Loading in Data')
    emulator_data = EmulatorData(directory=export_dir)
    print('2/4: Processing Data')
    emulator_data, train_features, test_features, train_labels, test_labels = emulator_data.process(
        target_column='sle',
        drop_missing=True,
        drop_columns=['groupname', 'experiment'],
        boolean_indices=True,
        scale=True,
        split_type='batch_test',
        drop_outliers={'column': 'ivaf', 'operator': '<', 'value': -1e13},
        time_series=True,
        lag=5,
    )
    
    data_dict = {'train_features': train_features,
                'train_labels': train_labels,
                'test_features': test_features,
                'test_labels': test_labels, }
    trainer = Trainer(cfg)

    print('3/4: Training Model')
    time_series_architecture = {
        'num_rnn_layers': 6,
        'num_rnn_hidden': 256,
    }

    trainer.train(
        model=TimeSeriesEmulator.TimeSeriesEmulator,
        architecture=time_series_architecture,
        data_dict=data_dict,
        criterion=nn.MSELoss(),
        epochs=100,
        batch_size=100,
        tensorboard=False,
        save_model=True,
        performance_optimized=True,
        sequence_length=5
    )

    print('4/4: Evaluating Model')
    model = trainer.model
    metrics, preds = trainer.evaluate()
    print(metrics)
    output_test_series(model, emulator_data, draws='random', k=10, save=True)


def lag_sequence_test(lag_array, sequence_array, iterations):
    count = 0
    for iteration in range(1, iterations+1):
        for lag in lag_array:
            for sequence_length in sequence_array:
                print(f"Training... Lag: {lag}, Sequence Length: {sequence_length}, Iteration: {iteration}, Trained {count} models")
                emulator_data = EmulatorData(directory=export_dir)
                emulator_data, train_features, test_features, train_labels, test_labels = emulator_data.process(
                    target_column='sle',
                    drop_missing=True,
                    drop_columns=['groupname', 'experiment'],
                    boolean_indices=True,
                    scale=True,
                    split_type='batch_test',
                    drop_outliers={'column': 'ivaf', 'operator': '<', 'value': -1e13},
                    time_series=True,
                    lag=lag,
                )

                # TODO: I should be able to use emulator_data.train_features but I get error "AttributeError: 'tuple' object has no attribute 'train_features'"
                data_dict = {'train_features': train_features,
                            'train_labels': train_labels,
                            'test_features': test_features,
                            'test_labels': test_labels, }
                trainer = Trainer(cfg)
                time_series_architecture = {
                    'num_rnn_layers': 3,
                    'num_rnn_hidden': 128,
                }
                current_time = datetime.now().strftime(r"%d-%m-%Y %H.%M.%S")
                trainer.train(
                    model=TimeSeriesEmulator.TimeSeriesEmulator,
                    architecture=time_series_architecture,
                    data_dict=data_dict,
                    criterion=nn.MSELoss(),
                    epochs=100,
                    batch_size=100,
                    tensorboard=True,
                    save_model=False,
                    performance_optimized=False,
                    verbose=False,
                    sequence_length=sequence_length,
                    tensorboard_comment=f" -- {current_time}, lag={lag}, sequence_length={sequence_length}"
                )
                metrics, preds = trainer.evaluate()
                print('Metrics:', metrics)
                
                count += 1
                

def rnn_architecture_test(rnn_layers_array, hidden_nodes_array, iterations):  
    emulator_data = EmulatorData(directory=export_dir)
    emulator_data, train_features, test_features, train_labels, test_labels = emulator_data.process(
        target_column='sle',
        drop_missing=True,
        drop_columns=['groupname', 'experiment'],
        boolean_indices=True,
        scale=True,
        split_type='batch_test',
        drop_outliers={'column': 'ivaf', 'operator': '<', 'value': -1e13},
        time_series=True,
        lag=5,  # TODO: update with results from lag_sequence_test
    )
    
    data_dict = {
        'train_features': train_features,
        'train_labels': train_labels,
        'test_features': test_features,
        'test_labels': test_labels,
    }
                   
    count = 0
    for iteration in range(1, iterations+1):
        for num_rnn_layers in rnn_layers_array:
            for num_rnn_hidden in hidden_nodes_array:
                print(f"Training... RNN Layers: {num_rnn_layers}, Hidden: {num_rnn_hidden}, Iteration: {iteration}, Trained {count} models")
            
                trainer = Trainer(cfg)
                time_series_architecture = {
                    'num_rnn_layers': num_rnn_layers,
                    'num_rnn_hidden': num_rnn_hidden,
                }
                current_time = datetime.now().strftime(r"%d-%m-%Y %H.%M.%S")
                trainer.train(
                    model=TimeSeriesEmulator.TimeSeriesEmulator,
                    architecture=time_series_architecture,
                    data_dict=data_dict,
                    criterion=nn.MSELoss(),
                    epochs=10,
                    batch_size=100,
                    tensorboard=True,
                    save_model=True,
                    performance_optimized=False,
                    verbose=False,
                    sequence_length=5, # TODO: update with results from lag_sequence_test
                    tensorboard_comment=f" -- {current_time}, num_rnn={num_rnn_layers}, num_hidden={num_rnn_hidden}"
                )
                # metrics, preds = trainer.evaluate()
                # print('Metrics:', metrics)
                
                count += 1

# TODO: make dense_architecture_test() that tests what dense layers should be at the end of the RNN


# TODO: Write function for dataset_tests and other tests I've done before (reproducibility!!!), use dict{'dataset1':['columns']} to loop

# dataset1 = ['mrro_anomaly', 'rhoi', 'rhow', 'groupname', 'experiment']
# dataset2 = ['mrro_anomaly', 'rhoi', 'rhow', 'groupname', 'experiment', 'ice_shelf_fracture', 'tier', ]
# dataset3 = ['mrro_anomaly', 'groupname', 'experiment']
# dataset4 = ['groupname', 'experiment']
# dataset5 = ['groupname', 'experiment', 'regions', 'tier']

# def dataset_tests(datasets)
# count = 0
# for iteration in range(5):
#     for dataset in ['dataset5']:
#         print('')
#         print(f"Training... Dataset: {dataset}, Iteration: {iteration}, Trained {count} models")
#         test_features = pd.read_csv(f'/users/pvankatw/emulator/src/data/ml/{dataset}/test_features.csv')
#         train_features = pd.read_csv(f'/users/pvankatw/emulator/src/data/ml/{dataset}/train_features.csv')
#         test_labels = pd.read_csv(f'/users/pvankatw/emulator/src/data/ml/{dataset}/test_labels.csv')
#         train_labels = pd.read_csv(f'/users/pvankatw/emulator/src/data/ml/{dataset}/train_labels.csv')
#         scenarios = pd.read_csv(f'/users/pvankatw/emulator/src/data/ml/{dataset}/test_scenarios.csv').values.tolist()
#
#
#         data_dict = {'train_features': train_features,
#                     'train_labels': train_labels,
#                     'test_features': test_features,
#                     'test_labels': test_labels,  }
#
#         start = time.time()
#         trainer = Trainer(cfg)
#         trainer.train(
#             model=ExploratoryModel.ExploratoryModel,
#             num_linear_layers=6,
#             nodes=[256, 128, 64, 32, 16, 1],
#             # num_linear_layers=12,
#             # nodes=[2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1],
#             data_dict=data_dict,
#             criterion=nn.MSELoss(),
#             epochs=100,
#             batch_size=100,
#             tensorboard=True,
#             save_model=True,
#             performance_optimized=False,
#         )
#         print(f'Total Time: {time.time() - start:0.4f} seconds')
#
#         print('4/4: Evaluating Model')
#
#         model = trainer.model
#         metrics, preds = trainer.evaluate()
#
#         count += 1

if __name__ == '__main__':
    # lag_sequence_test(
    #     lag_array=[1, 3, 5, 10],
    #     sequence_array=[3, 5, 10],
    #     iterations=5
    # )
    
    # run_network()

    # rnn_architecture_test(
    #     rnn_layers_array=[2, 4, 6, 10, 12], 
    #     hidden_nodes_array=[64, 128, 256], 
    #     iterations=5,
    #     )
    model = "02-12-2022 16.18.16.pt"
    metrics, preds = test_saved_network(
        path=f"/users/pvankatw/emulator/src/models/experiment_models/{model}", 
        architecture={'num_rnn_layers': 4,'num_rnn_hidden': 128,}
    )
    # import pandas as pd
    # pd.DataFrame(preds).to_csv(r'preds_3.csv')

stop = ''


