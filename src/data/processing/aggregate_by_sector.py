from data.classes.AtmosphereForcing import AtmosphereForcing
from data.classes.GridSectors import GridSectors
from data.classes.OceanForcing import OceanForcing
from data.classes.IceCollapse import IceCollapse
from utils import get_all_filepaths
import pandas as pd
import numpy as np
import time

def aggregate_by_sector(path):
    """Takes a atmospheric forcing dataset, adds sector numbers to it,
    and gets aggregate data based on sector and year. Returns atmospheric
    forcing data object.

    Args:
        path (str): path to atmospheric forcing nc file

    Returns:
        Obj: AtmosphereForcing instance with aggregated data
    """
    # Load grid data with 8km grid size
    
    print('')

    # Load in Atmospheric forcing data and add the sector numbers to it
    if 'Atmosphere' in path:
        grids = GridSectors(grid_size=8,)
        forcing = AtmosphereForcing(path=path)
        
    elif 'Ocean' in path:
        grids = GridSectors(grid_size=8, format_index=False)
        forcing = OceanForcing(aogcm_dir=path)
        
    elif 'Ice' in path:
        grids = GridSectors(grid_size=8,)
        forcing = IceCollapse(path)

    forcing = forcing.add_sectors(grids)

    
    # Group the dataset and assign aogcm column to the aogcm simulation
    if forcing.forcing_type in ('atmosphere', 'ice_collapse'):
        forcing.data = forcing.data.groupby(['sectors', 'year']).mean()
        forcing.data['aogcm'] = forcing.aogcm.lower()
    elif forcing.forcing_type == 'ocean':
        forcing.salinity_data = forcing.salinity_data.groupby(['sectors', 'year']).mean()
        forcing.salinity_data['aogcm'] = forcing.aogcm.lower()
        forcing.temperature_data = forcing.temperature_data.groupby(['sectors', 'year']).mean()
        forcing.temperature_data['aogcm'] = forcing.aogcm.lower()
        forcing.thermal_forcing_data = forcing.thermal_forcing_data.groupby(['sectors', 'year']).mean()
        forcing.thermal_forcing_data['aogcm'] = forcing.aogcm.lower()
    
    return forcing



# TODO: Maybe make each of these aggregate functions a method?
def aggregate_atmosphere(directory, export, model_in_columns=False,):
    """Loops through every NC file in the provided forcing directory
    from 1995-2100 and applies the aggregate_by_sector function. It then outputs
    the concatenation of all processed data to all_data.csv 

    Args:
        directory (str): Directory containing forcing files
    """
    start_time = time.time()

    # Get all NC files that contain data from 1995-2100
    filepaths = get_all_filepaths(path=directory, filetype='nc')
    filepaths = [f for f in filepaths if "1995-2100" in f]
    

    # Useful progress prints
    print(f"Files to be processed...")
    print([f.split("/")[-1] for f in filepaths])

    # Loop over each file specified above
    all_data = pd.DataFrame()
    for i, fp in enumerate(filepaths):
        print('')
        print(f'File {i+1} / {len(filepaths)}')
        print(f'File: {fp.split("/")[-1]}')
        print(f'Time since start: {(time.time()-start_time) // 60} minutes')

        # attach the sector to the data and groupby sectors & year
        forcing = aggregate_by_sector(fp)

        # Handle files that don't have mrro_anomaly input (ISPL RCP 85?)
        try:
            forcing.data['mrro_anomaly']
        except KeyError:
            forcing.data['mrro_anomaly'] = np.nan

        # Keep selected columns and output each file individually
        forcing.data = forcing.data[['pr_anomaly', 'evspsbl_anomaly', 'mrro_anomaly', 'smb_anomaly', 'ts_anomaly', 'regions', 'aogcm',]]
    
        # forcing.data.to_csv(f"{fp[:-3]}_sectoryeargrouped.csv")

        # meanwhile, create a concatenated dataset
        all_data = pd.concat([all_data, forcing.data])
            
        print(' -- ')
    
    
    if model_in_columns:
        data = {'atmospheric_forcing': all_data}
        all_data = aogcm_to_features(data=data, export_dir=export)
    
    else:
        if export:
            all_data.to_csv(f"{export}/atmospheric_forcing.csv")
        
        
def aggregate_ocean(directory, export, model_in_columns=False, ):
    """Loops through every NC file in the provided forcing directory
    from 1995-2100 and applies the aggregate_by_sector function. It then outputs
    the concatenation of all processed data to all_data.csv 


    Args:
        directory (str): Import directory for oceanic forcing files (".../Ocean_Forcing/")
        export (str): Export directory to store output files
        model_in_columns (bool, optional): Wither to format AOGCM model as columns. Defaults to False.
    """
    start_time = time.time()

    # Get all NC files that contain data from 1995-2100
    filepaths = get_all_filepaths(path=directory, filetype='nc')
    filepaths = [f for f in filepaths if "1995-2100" in f]
    
    # In the case of ocean forcings, use the filepaths of the files to determine
    # which directories need to be used for OceanForcing processing. Change to
    # those directories rather than individual files.
    aogcms = list(set([f.split('/')[-3] for f in filepaths]))
    filepaths = [f"{directory}/{aogcm}/" for aogcm in aogcms]

    # Useful progress prints
    print(f"Files to be processed...")
    print([f.split("/")[-2] for f in filepaths])

    # Loop over each directory specified above
    salinity_data = pd.DataFrame()
    temperature_data = pd.DataFrame()
    thermal_forcing_data = pd.DataFrame()
    for i, fp in enumerate(filepaths):
        print('')
        print(f'Directory {i+1} / {len(filepaths)}')
        print(f'Directory: {fp.split("/")[-2]}')
        print(f'Time since start: {(time.time()-start_time) // 60} minutes')

        # attach the sector to the data and groupby sectors & year
        forcing = aggregate_by_sector(fp)

        forcing.salinity_data = forcing.salinity_data[['salinity', 'regions', 'aogcm']]
        forcing.temperature_data = forcing.temperature_data[['temperature', 'regions', 'aogcm']]
        forcing.thermal_forcing_data = forcing.thermal_forcing_data[['thermal_forcing', 'regions', 'aogcm']]
        
        
        # meanwhile, create a concatenated dataset
        salinity_data = pd.concat([salinity_data, forcing.salinity_data])
        temperature_data = pd.concat([temperature_data, forcing.temperature_data])
        thermal_forcing_data = pd.concat([thermal_forcing_data, forcing.thermal_forcing_data])
        
        # salinity_data.to_csv(export+'/_salinity.csv')
        # temperature_data.to_csv(export+'/_temperature.csv')
        # thermal_forcing_data.to_csv(export+'/_thermal_forcing.csv')
        
    print(' -- ')
    
    if model_in_columns:
        # For each concatenated dataset
        data = {'salinity': salinity_data, 'temperature': temperature_data, 'thermal_forcing': thermal_forcing_data}
        all_data = aogcm_to_features(data, export_dir=export)
    
    else:
        if export:
            salinity_data.to_csv(export+'/salinity.csv')
            temperature_data.to_csv(export+'/temperature.csv')
            thermal_forcing_data.to_csv(export+'/thermal_forcing.csv')
            
def aggregate_icecollapse(directory, export, model_in_columns=False, ):
    """Loops through every NC file in the provided forcing directory
    from 1995-2100 and applies the aggregate_by_sector function. It then outputs
    the concatenation of all processed data to all_data.csv 


    Args:
        directory (str): Import directory for oceanic forcing files (".../Ocean_Forcing/")
        export (str): Export directory to store output files
        model_in_columns (bool, optional): Wither to format AOGCM model as columns. Defaults to False.
    """
    start_time = time.time()

    # Get all NC files that contain data from 1995-2100
    filepaths = get_all_filepaths(path=directory, filetype='nc')
    
    # In the case of ocean forcings, use the filepaths of the files to determine
    # which directories need to be used for OceanForcing processing. Change to
    # those directories rather than individual files.
    aogcms = list(set([f.split('/')[-2] for f in filepaths]))
    filepaths = [f"{directory}/{aogcm}/" for aogcm in aogcms]

    # Useful progress prints
    print(f"Files to be processed...")
    print([f.split("/")[-2] for f in filepaths])

    # Loop over each directory specified above
    ice_collapse = pd.DataFrame()
    for i, fp in enumerate(filepaths):
        print('')
        print(f'Directory {i+1} / {len(filepaths)}')
        print(f'Directory: {fp.split("/")[-2]}')
        print(f'Time since start: {(time.time()-start_time) // 60} minutes')

        # attach the sector to the data and groupby sectors & year
        forcing = aggregate_by_sector(fp)

        forcing.data = forcing.data[['mask', 'regions', 'aogcm']]
        
        
        # meanwhile, create a concatenated dataset
        ice_collapse = pd.concat([ice_collapse, forcing.data])

        
    print(' -- ')
    
    if model_in_columns:
        # For each concatenated dataset
        data = {'ice_collapse': ice_collapse,}
        all_data = aogcm_to_features(data, export_dir=export)
    
    else:
        if export:
            ice_collapse.to_csv(export+'/ice_collapse.csv')

            
            
# ! Deprecated -- not useful
def aogcm_to_features(data: dict, export_dir: str):
        
    for key, all_data in data.items():
        separate_aogcm_dataframes = [y for x, y in all_data.groupby('aogcm')]
        
        # Change columns names in each dataframe
        for df in separate_aogcm_dataframes:
            aogcm = df.aogcm.iloc[0]
            df.columns = [f"{x}_{aogcm}" if x not in ['sectors', 'year', 'region', 'aogcm'] else x for x in df.columns ]
            
        # Merge dataframes together on common columns [sectors, year], resulting in 
        # one dataframe with sector, year, region, and columns for each aogcm variables
        all_data = separate_aogcm_dataframes[0]
        all_data = all_data.drop(columns=['aogcm'])
    
        for df in separate_aogcm_dataframes[1:]:
            df = df.drop(columns=['aogcm'])
            all_data = pd.merge(all_data, df, on=['sectors', 'year',], how='outer')
            
        region_cols = [c for c in all_data.columns if 'region' in c]
        non_region_cols = [c for c in all_data.columns if 'region' not in c]
        all_data = all_data[non_region_cols]
        
        # region assignment produces NA's, low priority -- do later
        # all_data['region'] = separate_aogcm_dataframes[0][region_cols[0]].reset_index(drop=True)
        all_data = all_data.drop_duplicates() # See why there are duplicates -- until then, this works
        
        if export_dir:
                all_data.to_csv(f"{export_dir}/{key}.csv")
            
    return all_data