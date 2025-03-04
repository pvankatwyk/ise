ISE Documentation
=================

.. image:: https://readthedocs.org/projects/ise/badge/?version=latest
   :target: https://ise.readthedocs.io/en/latest/

ISE (**Ice Sheet Emulator**) is a Python package for training and analyzing **ice sheet emulators**, including **ISEFlow**, a flow-based neural network emulator designed for improved **sea level projections** and **uncertainty quantification**.

This repository supports emulation for both the **Antarctic** and **Greenland ice sheets**, enabling efficient predictions of **ice volume above flotation (IVAF)** changes using machine learning models.

About
=====
ISEFlow and other emulators in this package process **climate forcings** and **IVAF projections** from the `ISMIP6 simulations <https://app.globus.org/file-manager?origin_id=ad1a6ed8-4de0-4490-93a9-8258931766c7&origin_path=%2FAIS%2F>`_.

This codebase has been used in **peer-reviewed research**, including:

- *"A Variational LSTM Emulator of Sea Level Contribution From the Antarctic Ice Sheet"*
- *"ISEFlow: A Flow-Based Neural Network Emulator for Improved Sea Level Projections and Uncertainty Quantification"*

🔎 **For details on replication**, refer to the `Releases <https://github.com/Brown-SciML/ise/releases>`_ section.

📚 **Documentation:** `ISE ReadTheDocs <https://ise.readthedocs.io/>`_

Quickstart
==========
To get started, you must first have access to the Globus Archive containing the ISMIP6 climate forcings and ISMIP6 model outputs. For information on gaining access to these datasets, see the `ISMIP wiki page <https://theghub.org/groups/ismip6/wiki>`_.

Installation
------------
ISE uses `uv <https://github.com/astral-sh/uv>`_ for dependency management. To set up the environment:

.. code-block:: shell

   uv venv
   uv pip install -r requirements.txt

or using **pip** directly:

.. code-block:: shell

   pip install -r requirements.txt

To install in **editable mode** (for development):

.. code-block:: shell

   pip install -e .

Cloning the Repository
----------------------
To use it as a package, clone the repository by running:

.. code-block:: shell

   git clone https://github.com/Brown-SciML/ise.git

Then navigate to the cloned directory:

.. code-block:: shell

   cd ise

Usage
=====
Loading a Pretrained ISEFlow-AIS Model
--------------------------------------

.. code-block:: python

   from ise.models.ISEFlow import ISEFlow_AIS
   
   # Load v1.0.0 of ISEFlow-AIS
   iseflowais = ISEFlow_AIS.load(version="v1.0.0")

Running Predictions
-------------------

.. code-block:: python

   import numpy as np
   
   # Define Climate Forcings
   year = np.arange(2015, 2101)
   pr_anomaly = np.array([...])
   evspsbl_anomaly = np.array([...])
   smb_anomaly = np.array([...])
   ts_anomaly = np.array([...])
   ocean_thermal_forcing = np.array([...])
   ocean_salinity = np.array([...])
   ocean_temp = np.array([...])

   # Ice Sheet Model Characteristics
   initial_year = 1980
   numerics = 'fd'
   stress_balance = 'ho'
   resolution = 16
   init_method = "da"

   prediction, uq = iseflowais.predict(
       year, pr_anomaly, evspsbl_anomaly, smb_anomaly, ts_anomaly, ocean_thermal_forcing, ocean_salinity, ocean_temp,
       initial_year, numerics, stress_balance, resolution, init_method
   )

   print(prediction)
   print(uq['aleatoric'])
   print(uq['epistemic'])

Contributing
============
We welcome contributions! To get started:

1. **Fork the repository** on GitHub.
2. **Create a new branch** for your feature or bugfix.
3. **Submit a pull request** (PR) for review.

Run tests before submitting:

.. code-block:: shell

   pytest tests/

Known Issues & Future Work
==========================
- Creating more unit tests. I know, maybe one day I'll get around it.
- Expanding **support for additional climate scenarios** and additional ISM runs (ISMIP7).
- Better documentation and improvements to the readthedocs page.

Contact & Support
=================
This repository is actively maintained by **Peter Van Katwyk**, Ph.D. student at **Brown University**.

📩 **Email:** `peter_van_katwyk@brown.edu <mailto:peter_van_katwyk@brown.edu>`_  
🐙 **GitHub Issues:** `Report a bug <https://github.com/Brown-SciML/ise/issues>`_  

🚀 **ISE is a work in progress!** If you use this in research, please consider citing our work. See `CITATION.md` for details.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   docs/source/ise.rst
