import warnings

import numpy as np
import pandas as pd
import torch
from nflows import distributions, flows, transforms
from torch import nn, optim

from ise.data.dataclasses import EmulatorDataset
from ise.data.scaler import StandardScaler
from ise.utils.functions import to_tensor


class PCA(nn.Module):
    def __init__(self, n_components):

        """
        Principal Component Analysis (PCA) model.

        This class provides a PCA model which can be fit to data.

        Attributes:
            n_components (int or float): The number of components to keep. Can be an int or a float between 0 and 1.
            mean (torch.Tensor): The mean of the input data. Calculated during fit.
            components (torch.Tensor): The principal components. Calculated during fit.
            singular_values (torch.Tensor): The singular values corresponding to each of the principal components. Calculated during fit.
            explained_variance (torch.Tensor): The amount of variance explained by each of the selected components. Calculated during fit.
            explained_variance_ratio (torch.Tensor): Percentage of variance explained by each of the selected components. Calculated during fit.
        """
        super(PCA, self).__init__()
        self.n_components = n_components
        self.mean = None
        self.components = None
        self.singular_values = None
        self.explained_variance = None
        self.explained_variance_ratio = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.to(self.device)

    def fit(self, X):
        """
        Fit the PCA model to the input data.

        Args:
            X (np.array | pd.DataFrame): Input data, a tensor of shape (n_samples, n_features).

        Returns:
            self (PCModel): The fitted PCA model.

        Raises:
            ValueError: If n_components is not a float in the range (0, 1) or an integer.
        """
        # Center the data
        X = self._to_tensor(X)
        self.mean = torch.mean(X, dim=0)
        X_centered = X - self.mean

        # Compute low-rank PCA
        U, S, V = torch.pca_lowrank(
            X_centered,
            q=301,
        )

        # Compute total variance
        total_variance = S.pow(2).sum()
        explained_variance = S.pow(2)
        explained_variance_ratio = explained_variance / total_variance

        # Determine the number of components for the desired variance
        if isinstance(self.n_components, float) and 0 < self.n_components < 1:
            cumulative_variance_ratio = torch.cumsum(explained_variance_ratio, dim=0)
            # Number of components to explain desired variance
            num_components = torch.searchsorted(cumulative_variance_ratio, self.n_components) + 1
            self.n_components = min(num_components, S.size(0))
        elif isinstance(self.n_components, int):
            self.n_components = min(self.n_components, S.size(0))
        else:
            raise ValueError("n_components must be a float in the range (0, 1) or an integer.")

        self.components = V[:, : self.n_components]
        self.singular_values = S[: self.n_components]
        self.explained_variance = explained_variance[: self.n_components]
        self.explained_variance_ratio = explained_variance_ratio[: self.n_components]
        return self

    def transform(self, X):
        """
        Apply dimensionality reduction to the input data using the fitted PCA model.

        Args:
            X (np.array | pd.DataFrame): Input data, a tensor of shape (n_samples, n_features).

        Returns:
            torch.Tensor: Transformed data, a tensor of shape (n_samples, n_components).

        Raises:
            RuntimeError: If the PCA model has not been fitted yet.
        """
        X = self._to_tensor(X)
        if self.mean is None or self.components is None:
            raise RuntimeError("PCA model has not been fitted yet.")
        X_centered = X - self.mean
        return torch.mm(X_centered, self.components)

    def inverse_transform(self, X):
        """
        Apply inverse dimensionality reduction to the input data using the fitted PCA model.

        Args:
            X (np.array | pd.DataFrame): Transformed data, a tensor of shape (n_samples, n_components).

        Returns:
            torch.Tensor: Inverse transformed data, a tensor of shape (n_samples, n_features).

        Raises:
            RuntimeError: If the PCA model has not been fitted yet.
        """
        X = self._to_tensor(X)

        if self.mean is None or self.components is None:
            raise RuntimeError("PCA model has not been fitted yet.")
        inverse = torch.mm(X, self.components.t()) + self.mean
        return inverse

    def save(self, path):
        """
        Save the PCA model to a file.

        Args:
            path (str): The path to save the model.

        Raises:
            RuntimeError: If the PCA model has not been fitted yet.
        """
        if self.mean is None or self.components is None:
            raise RuntimeError("PCA model has not been fitted yet.")
        torch.save(
            {
                "n_components": self.n_components,
                "mean": self.mean,
                "components": self.components,
                "singular_values": self.singular_values,
                "explained_variance": self.explained_variance,
                "explained_variance_ratio": self.explained_variance_ratio,
            },
            path,
        )

    def _to_tensor(self, x):
        """
        Converts the input data to a PyTorch tensor.

        Args:
            x: The input data to be converted.

        Returns:
            The converted PyTorch tensor.

        Raises:
            ValueError: If the input data is not a pandas DataFrame, numpy array, or PyTorch tensor.
        """
        if x is None:
            return None
        if isinstance(x, pd.DataFrame):
            x = x.values
        elif isinstance(x, np.ndarray):
            x = torch.tensor(x)
        elif isinstance(x, torch.Tensor):
            pass
        else:
            raise ValueError("Data must be a pandas dataframe, numpy array, or PyTorch tensor")

        return x

    @staticmethod
    def load(path):
        """
        Load a saved PCA model from a file.

        Args:
            path (str): The path to the saved model.

        Returns:
            PCA: The loaded PCA model.

        Raises:
            FileNotFoundError: If the file does not exist.
            RuntimeError: If the loaded model is not a PCA model.
        """
        checkpoint = torch.load(path)
        model = PCA(checkpoint["n_components"])
        model.mean = checkpoint["mean"]
        model.components = checkpoint["components"]
        model.singular_values = checkpoint["singular_values"]
        model.explained_variance = checkpoint["explained_variance"]
        model.explained_variance_ratio = checkpoint["explained_variance_ratio"]
        return model


class DimensionProcessor(nn.Module):
    def __init__(
        self,
        pca_model,
        scaler_model,
    ):
        super(DimensionProcessor, self).__init__()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # LOAD PCA
        if isinstance(pca_model, str):
            self.pca = PCA.load(pca_model)
        elif isinstance(pca_model, PCA):
            self.pca = pca_model
        else:
            raise ValueError("pca_model must be a path (str) or a PCA instance")
        if self.pca.mean is None or self.pca.components is None:
            raise RuntimeError("PCA model has not been fitted yet.")

        # LOAD SCALER
        if isinstance(scaler_model, str):
            self.scaler = StandardScaler.load(scaler_model)
        elif isinstance(scaler_model, PCA):
            self.scaler = scaler_model
        else:
            raise ValueError("pca_model must be a path (str) or a PCA instance")
        if self.scaler.mean_ is None or self.scaler.scale_ is None:
            raise RuntimeError("This StandardScalerPyTorch instance is not fitted yet.")

        self.scaler.to(self.device)
        self.pca.to(self.device)
        self.to(self.device)

    def to_pca(self, data):
        data = data.to(self.device)
        scaled = self.scaler.transform(data)  # scale
        return self.pca.transform(scaled)  # convert to pca

    def to_grid(self, pcs, unscale=True):
        if not isinstance(pcs, torch.Tensor):
            if isinstance(pcs, pd.DataFrame):
                pcs = pcs.values
            pcs = torch.tensor(pcs, dtype=torch.float32).to(self.device)
        else:
            pcs = pcs.to(self.device)
        # Ensure components and mean are on the same device as pcs
        components = self.pca.components.to(self.device)
        pca_mean = self.pca.mean.to(self.device)
        # Now, the operation should not cause a device mismatch error
        scaled_grid = torch.mm(pcs, components.t()) + pca_mean

        if unscale:
            scale = self.scaler.scale_.to(self.device)
            scaler_mean = self.scaler.mean_.to(self.device)
            unscaled_grid = scaled_grid * scale + scaler_mean
            return unscaled_grid

        return scaled_grid


class WeakPredictor(nn.Module):
    def __init__(
        self,
        lstm_num_layers,
        lstm_hidden_size,
        input_size=28,
        output_size=1,
        dim_processor=None,
        scaler_path=None,
        ice_sheet="AIS",
        criterion=torch.nn.MSELoss(),
    ):
        super(WeakPredictor, self).__init__()
        
        self.lstm_num_layers = lstm_num_layers
        self.lstm_num_hidden = lstm_hidden_size

        self.input_size = input_size
        self.output_size = output_size
        self.ice_sheet = ice_sheet
        self.ice_sheet_dim = (761, 761) if ice_sheet == "AIS" else (337, 577)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.to(self.device)

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=lstm_hidden_size,
            batch_first=True,
            num_layers=lstm_num_layers,
        )
        self.relu = nn.ReLU()
        self.linear1 = nn.Linear(in_features=lstm_hidden_size, out_features=32)
        # self.linear2 = nn.Linear(in_features=512, out_features=256)
        self.linear_out = nn.Linear(in_features=32, out_features=output_size)

        self.optimizer = optim.Adam(
            self.parameters(),
        )
        
        self.criterion = criterion
        self.trained = False

        if isinstance(dim_processor, DimensionProcessor):
            self.dim_processor = dim_processor.to(self.device)
        elif isinstance(dim_processor, str) and scaler_path is None:
            raise ValueError(
                "If dim_processor is a path to a PCA object, scaler_path must be provided"
            )
        elif isinstance(dim_processor, str) and scaler_path is not None:
            self.dim_processor = DimensionProcessor(
                pca_model=self.pca_model, scaler_model=scaler_path
            ).to(self.device)
        elif dim_processor is None:
            self.dim_processor = None
        else:
            raise ValueError(
                "dim_processor must be a DimensionProcessor instance or a path (str) to a PCA object with scaler_path specified as a Scaler object."
            )

    def forward(self, x):
        batch_size = x.shape[0]
        h0 = (
            torch.zeros(self.lstm_num_layers, batch_size, self.lstm_num_hidden)
            .requires_grad_()
            .to(self.device)
        )
        c0 = (
            torch.zeros(self.lstm_num_layers, batch_size, self.lstm_num_hidden)
            .requires_grad_()
            .to(self.device)
        )
        _, (hn, _) = self.lstm(x, (h0, c0))
        x = hn[-1, :, :]

        x = self.linear1(x)
        x = self.relu(x)
        # x = self.linear2(x)
        # x = self.relu(x)
        x = self.linear_out(x)

        return x

    def fit(
        self, X, y, epochs=100, sequence_length=5, batch_size=64, loss=None, val_X=None, val_y=None
    ):
        X, y = to_tensor(X).to(self.device), to_tensor(y).to(self.device)

        if val_X is not None and val_y is not None:  # not val_X.empty and not val_y.empty:
            validate = True
        else:
            validate = False
        if loss is not None:
            self.criterion = loss.to(self.device)
        elif loss is None and self.criterion is None:
            raise ValueError("loss must be provided if criterion is None.")

        self.criterion = self.criterion.to(self.device)

        if isinstance(X, pd.DataFrame):
            X = X.values
        if isinstance(y, pd.DataFrame):
            y = y.values

        dataset = EmulatorDataset(X, y, sequence_length=sequence_length)
        data_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
        self.train()
        self.to(self.device)
        for epoch in range(1, epochs + 1):
            self.train()
            batch_losses = []
            for i, (x, y) in enumerate(data_loader):
                x = x.to(self.device)
                y = y.to(self.device)
                # batch_size = x.shape[0]
                self.optimizer.zero_grad()
                y_pred = self.forward(x)

                # idk if the grid loss is working...
                # y_pred = self.dim_processor.to_grid(y_pred, unscale=False).reshape(batch_size, self.ice_sheet_dim[0], self.ice_sheet_dim[1])
                # y_true = self.dim_processor.to_grid(y, unscale=False).reshape(batch_size, self.ice_sheet_dim[0], self.ice_sheet_dim[1])

                # loss = self.criterion(y_true, y_pred, smoothness_weight=0, extreme_value_threshold=1e-6)
                loss = self.criterion(y_pred, y)
                loss.backward()
                self.optimizer.step()
                batch_losses.append(loss.item())

                # if i % 10 == 0:
                #     print(f"Epoch: {epoch}, Batch: {i}, Loss: {loss.item()}")

            # self.scheduler.step()
            if validate:
                val_preds = self.predict(
                    val_X, sequence_length=sequence_length, batch_size=batch_size
                ).to(self.device)
                val_loss = self.criterion(
                    val_preds, torch.tensor(val_y.to_numpy(), device=self.device)
                )
                print(
                    f"Epoch {epoch}, Average Batch Loss: {sum(batch_losses) / len(batch_losses)}, Validation Loss: {val_loss}"
                )

            else:
                average_batch_loss = sum(batch_losses) / len(batch_losses)
                print(f"Epoch {epoch}, Average Batch Loss: {average_batch_loss}")

        self.trained = True

    def predict(self, X, sequence_length=5, batch_size=64):
        self.eval()
        self.to(self.device)
        if isinstance(X, pd.DataFrame):
            X = X.values

        dataset = EmulatorDataset(X, y=None, sequence_length=sequence_length)
        data_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=False)

        X = to_tensor(X).to(self.device)

        preds = torch.tensor([]).to(self.device)
        for X_test_batch in data_loader:
            self.eval()
            X_test_batch = X_test_batch.to(self.device)
            y_pred = self.forward(X_test_batch)
            # y_pred = self.dim_processor.to_grid(y_pred)
            preds = torch.cat((preds, y_pred), 0)

        return preds


class DeepEnsemble(nn.Module):
    def __init__(
        self, weak_predictors: list = [], forcing_size=27, sle_size=1, num_predictors=3
    ):
        super(DeepEnsemble, self).__init__()

        if not weak_predictors:
            if forcing_size is None or sle_size is None:
                raise ValueError(
                    "forcing_size and sle_size must be provided if weak_predictors is not provided"
                )
            self.weak_predictors = [
                WeakPredictor(
                    lstm_num_layers=np.random.randint(low=1, high=3, size=1)[0],
                    lstm_hidden_size=np.random.choice([512, 256, 128, 64], 1)[0],
                )
                for _ in range(num_predictors)
            ]
        else:
            if isinstance(weak_predictors, list):
                self.weak_predictors = weak_predictors
                if not all([isinstance(x, WeakPredictor) for x in weak_predictors]):
                    raise ValueError("weak_predictors must be a list of WeakPredictor instances")
            else:
                raise ValueError("weak_predictors must be a list of WeakPredictor instances")

            if any([x for x in weak_predictors if not isinstance(x, WeakPredictor)]):
                raise ValueError("weak_predictors must be a list of WeakPredictor instances")

        # check to see if all weak predictors are trained
        self.trained = all([wp.trained for wp in self.weak_predictors])

    def forward(self, x):
        if not self.trained:
            warnings.warn("This model has not been trained. Predictions will not be accurate.")
        mean_prediction = torch.mean(torch.stack([wp.predict(x) for wp in self.weak_predictors], axis=1), axis=1).squeeze()
        epistemic_uncertainty = torch.std(torch.stack([wp.predict(x) for wp in self.weak_predictors], axis=1), axis=1).squeeze()
        return mean_prediction, epistemic_uncertainty
    
    def predict(self, x):
        return self.forward(x)

    def fit(
        self,
        X,
        y,
        epochs=100,
        batch_size=64,
    ):
        if self.trained:
            warnings.warn("This model has already been trained. Training anyways.")
        for i, wp in enumerate(self.weak_predictors):
            print(f"Training Weak Predictor {i+1} of {len(self.weak_predictors)}:")
            wp.fit(X, y, epochs, batch_size)
            print("")
        self.trained = True


class NormalizingFlow(nn.Module):
    def __init__(
        self,
        forcing_size=27,
        sle_size=1,
    ):
        super(NormalizingFlow, self).__init__()
        self.num_flow_transforms = 5
        self.num_input_features = forcing_size
        self.num_predicted_sle = sle_size
        self.flow_hidden_features = sle_size * 2
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.to(self.device)

        self.base_distribution = distributions.normal.ConditionalDiagonalNormal(
            shape=[self.num_predicted_sle],
            context_encoder=nn.Linear(self.num_input_features, self.flow_hidden_features),
        )

        t = []
        for _ in range(self.num_flow_transforms):
            t.append(
                transforms.permutations.RandomPermutation(
                    features=self.num_predicted_sle,
                )
            )
            t.append(
                transforms.autoregressive.MaskedAffineAutoregressiveTransform(
                    features=self.num_predicted_sle,
                    hidden_features=self.flow_hidden_features,
                    context_features=self.num_input_features,
                )
            )

        self.t = transforms.base.CompositeTransform(t)

        self.flow = flows.base.Flow(transform=self.t, distribution=self.base_distribution)

        self.optimizer = optim.Adam(self.flow.parameters())
        self.criterion = self.flow.log_prob
        self.trained = False
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.to(self.device)

    def fit(self, X, y, epochs=100, batch_size=64):
        X, y = to_tensor(X).to(self.device), to_tensor(y).to(self.device)
        dataset = EmulatorDataset(X, y, sequence_length=1)
        data_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)
        self.train()

        for epoch in range(1, epochs + 1):
            epoch_loss = []
            for i, (x, y) in enumerate(data_loader):
                x = x.to(self.device).view(x.shape[0], -1)
                y = y.to(self.device)
                self.optimizer.zero_grad()
                loss = torch.mean(-self.flow.log_prob(inputs=y, context=x))
                loss.backward()
                self.optimizer.step()
                epoch_loss.append(loss.item())
            print(f"Epoch {epoch}, Loss: {sum(epoch_loss) / len(epoch_loss)}")
        self.trained = True

    def sample(self, features, num_samples, return_type="numpy"):
        if not isinstance(features, torch.Tensor):
            features = to_tensor(features)
        samples = self.flow.sample(num_samples, context=features).reshape(
            features.shape[0], num_samples
        )
        if return_type == "tensor":
            pass
        elif return_type == "numpy":
            samples = samples.detach().cpu().numpy()
        else:
            raise ValueError("return_type must be 'numpy' or 'tensor'")
        return samples

    def get_latent(self, x, latent_constant=0.0):
        x = to_tensor(x).to(self.device)
        # latent_constant = torch.tensor(latent_constant).to(self.device)
        latent_constant_tensor = torch.ones((x.shape[0], 1)).to(self.device) * latent_constant
        z, _ = self.t(latent_constant_tensor.float(), context=x)
        return z

    def aleatoric(self, features, num_samples):
        if not isinstance(features, torch.Tensor):
            features = to_tensor(features)
        samples = self.flow.sample(num_samples, context=features)
        samples = samples.detach().cpu().numpy()
        std = np.std(samples, axis=1).squeeze()
        return std


class HybridEmulator(torch.nn.Module):
    def __init__(self, deep_ensemble, normalizing_flow):
        super(HybridEmulator, self).__init__()

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.to(self.device)

        if not isinstance(deep_ensemble, DeepEnsemble):
            raise ValueError("deep_ensemble must be a DeepEmulator instance")
        if not isinstance(normalizing_flow, NormalizingFlow):
            raise ValueError("normalizing_flow must be a NormalizingFlow instance")

        self.deep_ensemble = deep_ensemble.to(self.device)
        self.normalizing_flow = normalizing_flow.to(self.device)
        self.trained = self.deep_ensemble.trained and self.normalizing_flow.trained

    def fit(self, X, y, epochs=100, nf_epochs=None, de_epochs=None):
        # if specific epoch numbers are not supplied, use the same number of epochs for both
        if nf_epochs is None:
            nf_epochs = epochs
        if de_epochs is None:
            de_epochs = epochs
            
        X, y = to_tensor(X).to(self.device), to_tensor(y).to(self.device)
        if self.trained:
            warnings.warn("This model has already been trained. Training anyways.")
        if not self.normalizing_flow.trained:
            print(f"\nTraining Normalizing Flow ({nf_epochs} epochs):")
            self.normalizing_flow.fit(X, y, epochs=nf_epochs)
        z = self.normalizing_flow.get_latent(X,).detach()
        X_latent = torch.concatenate((X, z), axis=1)
        if not self.deep_ensemble.trained:
            print(f"\nTraining Deep Ensemble ({de_epochs} epochs):")
            self.deep_ensemble.fit(X_latent, y, epochs=de_epochs)
        self.trained = True

    def forward(self, x):
        x = to_tensor(x).to(self.device)
        if not self.trained:
            warnings.warn("This model has not been trained. Predictions will not be accurate.")
        z = self.normalizing_flow.get_latent(x, ).detach()
        X_latent = torch.concatenate((x, z), axis=1)
        prediction, epistemic = self.deep_ensemble(X_latent)
        aleatoric = self.normalizing_flow.aleatoric(x, 100)
        return prediction, epistemic, aleatoric
    
    def save(self, path):
        torch.save(self.state_dict(), path)
    
    @staticmethod
    def load(path, deep_ensemble, normalizing_flow):
        model = HybridEmulator(deep_ensemble, normalizing_flow)
        model.load_state_dict(torch.load(path))
        return model
