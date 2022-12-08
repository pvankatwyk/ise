from ise.models.training.Trainer import Trainer
from ise.models.traditional import ExploratoryModel
from ise.models.timeseries.TimeSeriesEmulator import TimeSeriesEmulator
from ise.models.traditional.ExploratoryModel import ExploratoryModel
from ise.models.gp.GaussianProcess import GP
from torch import nn
import pandas as pd
import os
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF
import numpy as np
np.random.seed(10)
from sklearn.metrics import r2_score
from sklearn.decomposition import PCA



def train_timeseries_network(data_directory, 
                             architecture=None, 
                             epochs=20, 
                             batch_size=100, 
                             model=TimeSeriesEmulator,
                             loss=nn.MSELoss(),
                             tensorboard=False,
                             save_model=False,
                             performance_optimized=False,
                             verbose=False,
                             tensorboard_comment=None
                             ):
    
    if verbose:
        print('1/3: Loading processed data...')
    try:
        test_features = pd.read_csv(f'{data_directory}/ts_test_features.csv')
        train_features = pd.read_csv(f'{data_directory}/ts_train_features.csv')
        test_labels = pd.read_csv(f'{data_directory}/ts_test_labels.csv')
        train_labels = pd.read_csv(f'{data_directory}/ts_train_labels.csv')
        scenarios = pd.read_csv(f'{data_directory}/ts_test_scenarios.csv').values.tolist()
    except FileNotFoundError:
            raise FileNotFoundError('Files not found. Format must be in format \"ts_train_features.csv\"')
        
    data_dict = {'train_features': train_features,
                'train_labels': train_labels,
                'test_features': test_features,
                'test_labels': test_labels, }
    
    trainer = Trainer()
    if verbose:
        print('2/3: Training Model...')
        
    if architecture is None:
        architecture = {
            'num_rnn_layers': 4,
            'num_rnn_hidden': 128,
        }
    
    print('Architecture: ')
    print(architecture)

    trainer.train(
        model=model,
        architecture=architecture,
        data_dict=data_dict,
        criterion=loss,
        epochs=epochs,
        batch_size=batch_size,
        tensorboard=tensorboard,
        save_model=save_model,
        performance_optimized=performance_optimized,
        sequence_length=5,
        verbose=verbose,
        tensorboard_comment=tensorboard_comment,
    )

    if verbose:
        print('3/3: Evaluating Model')
    model = trainer.model
    metrics, test_preds = trainer.evaluate(verbose=verbose)
    return model, metrics, test_preds


def train_traditional_network(data_directory, 
                             architecture=None, 
                             epochs=20, 
                             batch_size=100, 
                             model=ExploratoryModel,
                             loss=nn.MSELoss(),
                             tensorboard=False,
                             save_model=False,
                             performance_optimized=False,
                             verbose=False,
                             tensorboard_comment=None
                             ):
    
    if verbose:
        print('1/3: Loading processed data')
    
    try:
        test_features = pd.read_csv(f'{data_directory}/traditional_test_features.csv')
        train_features = pd.read_csv(f'{data_directory}/traditional_train_features.csv')
        test_labels = pd.read_csv(f'{data_directory}/traditional_test_labels.csv')
        train_labels = pd.read_csv(f'{data_directory}/traditional_train_labels.csv')
        scenarios = pd.read_csv(f'{data_directory}/traditional_test_scenarios.csv').values.tolist()
    except FileNotFoundError:
            raise FileNotFoundError('Files not found. Format must be in format \"traditional_train_features.csv\"')
    
    if 'lag' in train_features.columns:
        raise AttributeError('Data must be processed using timeseries=True in feataure_engineering. Rerun feature engineering to train traditional network.')
        
    data_dict = {'train_features': train_features,
                'train_labels': train_labels,
                'test_features': test_features,
                'test_labels': test_labels, }
    
    trainer = Trainer()
    if verbose:
        print('2/3: Training Model')
        
    if architecture is None:
        architecture = {
            'num_linear_layers': 4,
            'nodes': [128, 64, 32, 1],
        }

    trainer.train(
        model=model,
        architecture=architecture,
        data_dict=data_dict,
        criterion=loss,
        epochs=epochs,
        batch_size=batch_size,
        tensorboard=tensorboard,
        save_model=save_model,
        performance_optimized=performance_optimized,
        sequence_length=5,
        verbose=verbose,
        tensorboard_comment=tensorboard_comment,
    )

    if verbose:
        print('3/3: Evaluating Model')
    model = trainer.model
    metrics, test_preds = trainer.evaluate(verbose=verbose)
    return metrics, test_preds

def train_gaussian_process(data_directory, n, features=['temperature'], sampling_method='random', kernel=None, verbose=False, save_directory=None):
    
    if verbose:
        print('1/3: Loading processed data...')
    
    try:
        test_features = pd.read_csv(f'{data_directory}/traditional_test_features.csv')
        train_features = pd.read_csv(f'{data_directory}/traditional_train_features.csv')
        test_labels = pd.read_csv(f'{data_directory}/traditional_test_labels.csv')
        train_labels = pd.read_csv(f'{data_directory}/traditional_train_labels.csv')
        scenarios = pd.read_csv(f'{data_directory}/traditional_test_scenarios.csv').values.tolist()
    except FileNotFoundError:
        test_features = pd.read_csv(f'{data_directory}/ts_test_features.csv')
        train_features = pd.read_csv(f'{data_directory}/ts_train_features.csv')
        test_labels = pd.read_csv(f'{data_directory}/ts_test_labels.csv')
        train_labels = pd.read_csv(f'{data_directory}/ts_train_labels.csv')
        scenarios = pd.read_csv(f'{data_directory}/ts_test_scenarios.csv').values.tolist()
    
    if not isinstance(features, list):
        raise ValueError(f'features argument must be a list, received {type(features)}')
    
    
    
    # if all the provided features are in the column list
    if all([f in train_features.columns for f in features]):    
        train_labels = np.array(train_labels.loc[train_features.index]).reshape(-1, 1)
        test_features = test_features[features]
        if isinstance(test_features, pd.Series) or test_features.shape[1] == 1:
            test_features = np.array(test_features).reshape(-1, 1)
    elif 'pc1' in features:
        train_features['set'] = 'train'
        test_features['set'] = 'test'
        features = pd.concat([train_features, test_features])
        pca = PCA(n_components=1)
        principalComponents = pca.fit_transform(features.drop(columns=['set']))
        train_features = principalComponents[features['set'] == 'train'].squeeze()
        test_features = principalComponents[features['set'] == 'test'].squeeze()
        
    if sampling_method.lower() == 'random':
        gp_train_features = train_features[features].sample(n)
    elif sampling_method.lower() == 'first_n':
        gp_train_features = train_features[features][:n]
    else:
        raise ValueError(f'sampling method must be in [random, first_n], received {sampling_method}')
        
    if kernel is None:
        kernel = RBF(length_scale=1.0, length_scale_bounds=(1e-6, 1e2))
    
    gaussian_process = GP(kernel=kernel)
    
    if verbose:
        print('2/3: Training Model...')
    gaussian_process.train(gp_train_features, gp_train_labels,)
    
    if verbose:
        print('3/3: Evaluating Model')
    preds, std_prediction, metrics = gaussian_process.test(gp_test_features, test_labels)
        
    if save_directory:
        if isinstance(save_directory, str):
            preds_path = f"{save_directory}/preds.csv"
            uq_path = f"{save_directory}/std.csv"
            
        elif isinstance(save_directory, bool):
            preds_path = f"preds.csv"
            uq_path = f"std.csv"
        
        pd.Series(preds, name='preds').to_csv(preds_path, index=False)
        pd.Series(std_prediction, name='std_prediction').to_csv(uq_path, index=False)

    
    return preds, std_prediction, metrics