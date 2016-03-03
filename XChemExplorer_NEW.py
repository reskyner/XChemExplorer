import os, sys, glob
import getopt

# diffraction image viewing only possible at DLS
sys.path.append('/dls_sw/apps/albula/3.1/dectris/albula/3.1/python')
try:
    import dectris.albula
except (ImportError,RuntimeError):
    pass

from PyQt4 import QtGui, QtCore, QtWebKit

import pickle
import base64
import math
import multiprocessing

sys.path.append(os.path.join(os.getenv('XChemExplorer_DIR'),'lib'))
from XChemUtils import parse
from XChemUtils import external_software
from XChemUtils import helpers
import XChemThread
import XChemDB
import XChemDialogs
import XChemPANDDA

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
import numpy as np

class XChemExplorer(QtGui.QApplication):
    def __init__(self,args):
        QtGui.QApplication.__init__(self,args)

        # general settings
        self.allowed_unitcell_difference_percent=5
        self.filename_root='${samplename}'
        self.data_source_set=False

        # Settings @ Directories
        self.current_directory=os.getcwd()
        if 'labxchem' in self.current_directory:
            self.project_directory='/'+os.path.join(*self.current_directory.split('/')[1:6])    # need splat operator: *
            self.beamline_directory=os.path.join(self.project_directory,'processing','beamline')
            self.initial_model_directory=os.path.join(self.project_directory,'processing','analysis','initial_model')
            self.refine_model_directory=os.path.join(self.project_directory,'processing','analysis','refine_model')
            self.reference_directory=os.path.join(self.project_directory,'processing','reference')
            self.database_directory=os.path.join(self.project_directory,'processing','database')
            self.data_source_file=''
            if os.path.isfile(os.path.join(self.project_directory,'processing','lab36','soakDBDataFile.sqlite')):
                self.data_source_file='soakDBDataFile.sqlite'
                self.database_directory=os.path.join(self.project_directory,'processing','lab36')
                self.data_source_set=True
                XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).create_missing_columns()
            self.ccp4_scratch_directory=os.path.join(self.project_directory,'processing','tmp')

            if not os.path.isdir(self.beamline_directory):
                os.mkdir(self.beamline_directory)
            if not os.path.isdir(os.path.join(self.project_directory,'processing','analysis')):
                os.mkdir(os.path.join(self.project_directory,'processing','analysis'))
            if not os.path.isdir(self.initial_model_directory):
                os.mkdir(self.initial_model_directory)
            if not os.path.isdir(self.reference_directory):
                os.mkdir(self.reference_directory)
            if not os.path.isdir(self.database_directory):
                os.mkdir(self.database_directory)
            if not os.path.isdir(self.ccp4_scratch_directory):
                os.mkdir(self.ccp4_scratch_directory)

            self.panddas_directory=''

        else:
            self.project_directory=self.current_directory
            self.beamline_directory=self.current_directory
            self.initial_model_directory=self.current_directory
            self.refine_model_directory=self.current_directory
            self.reference_directory=self.current_directory
            self.database_directory=self.current_directory
            self.data_source_file=''
            self.ccp4_scratch_directory=os.getenv('CCP4_SCR')
            self.panddas_directory=self.current_directory


        self.settings =     {'current_directory':       self.current_directory,
                             'project_directory':       self.project_directory,
                             'beamline_directory':      self.beamline_directory,
                             'initial_model_directory': self.initial_model_directory,
                             'refine_model_directory':  self.refine_model_directory,
                             'panddas_directory':       self.panddas_directory,
                             'reference_directory':     self.reference_directory,
                             'database_directory':      self.database_directory,
                             'data_source':             os.path.join(self.database_directory,self.data_source_file),
                             'ccp4_scratch':            self.ccp4_scratch_directory,
                             'unitcell_difference':     self.allowed_unitcell_difference_percent,
                             'filename_root':           self.filename_root   }


        # Settings @ Lists
        self.data_collection_list=[]
        self.visit_list=[]
        self.target=''
        self.dataset_outcome_combobox_dict={}
        self.data_collection_dict={}
        self.data_collection_statistics_dict={}
        self.initial_model_dimple_dict={}       # contains toggle button if dimple should be run
        self.reference_file_list=[]
        self.all_columns_in_data_source=XChemDB.data_source(os.path.join(self.database_directory,
                                                                         self.data_source_file)).return_column_list()
        self.albula_button_dict={}
        self.xtalform_dict={}

        self.dataset_outcome_dict={}            # contains the dataset outcome buttons
        self.data_collection_table_dict={}      # contains the dataset table
        self.data_collection_image_dict={}
        self.data_collection_column_three_dict={}
        self.main_data_collection_table_exists=False

        # command line arguments
        try:
            opts, args = getopt.getopt(sys.argv[1:], "hc:b:d:", ["help", "config=","beamline=","datasource="])
        except getopt.GetoptError:
            print 'Sorry, command line option does not exist'
            sys.exit()
        for o, a in opts:
            if o in ("-h", "--help"):
                print 'avail able command line options:'
                print '-c,--config:     config file'
                print '-b,--beamline:   beamline directory'
                print '-d,--datasource: data source file'
                sys.exit()
            elif o in ("-c", "--config"):
                pickled_settings = pickle.load(open(os.path.abspath(a),"rb"))
                self.beamline_directory=pickled_settings['beamline_directory']
                self.settings['beamline_directory']=self.beamline_directory
                self.initial_model_directory=pickled_settings['initial_model_directory']
                self.settings['initial_model_directory']=self.initial_model_directory
                self.database_directory=pickled_settings['database_directory']
                self.settings['database_directory']=self.database_directory
                self.data_source_file=pickled_settings['data_source']
                self.settings['data_source']=os.path.join(self.database_directory,self.data_source_file)
                if os.path.isfile(self.settings['data_source']):
                    XChemDB.data_source(self.settings['data_source']).create_missing_columns()
                    self.data_source_set=True
                else:       # in case just an empty file was specified
                    XChemDB.data_source(self.settings['data_source']).create_empty_data_source_file()
                    self.data_source_set=True
                self.ccp4_scratch_directory=pickled_settings['ccp4_scratch']
                self.settings['ccp4_scratch']=self.ccp4_scratch_directory
                self.allowed_unitcell_difference_percent=pickled_settings['unitcell_difference']
            elif o in ("-b", "--beamline"):
                self.beamline_directory=os.path.abspath(a)
            elif o in ("-d", "--datasource"):
                tmp=os.path.abspath(a)
                self.database_directory=tmp[:tmp.rfind('/')]
                self.data_source_file=tmp[tmp.rfind('/')+1:]
                self.settings['data_source']=os.path.join(self.database_directory,self.data_source_file)
                if os.path.isfile(self.settings['data_source']):
                    XChemDB.data_source(self.settings['data_source']).create_missing_columns()
                else:
                    XChemDB.data_source(self.settings['data_source']).create_empty_data_source_file()
                self.data_source_set=True


        self.target_list,self.visit_list=self.get_target_and_visit_list()

        # Settings @ Switches
        self.explorer_active=0
        self.coot_running=0
        self.progress_bar_start=0
        self.progress_bar_step=0
        self.albula = None
        self.albula_subframes=[]
        self.show_diffraction_image = None

        self.dataset_outcome = {    "success":                      "rgb(200,200,200)",
                                    "Failed - centring failed":     "rgb(200,200,200)",
                                    "Failed - no diffraction":      "rgb(200,200,200)",
                                    "Failed - processing barfs":    "rgb(200,200,200)",
                                    "Failed - loop empty":          "rgb(200,200,200)",
                                    "Failed - low resolution":      "rgb(200,200,200)",
                                    "Failed - no X-rays":           "rgb(200,200,200)",
                                    "Failed - unknown":             "rgb(200,200,200)"  }

        # checking for external software packages
        self.external_software=external_software().check()

        self.start_GUI()
        self.exec_()

    def get_target_and_visit_list(self):
        target_list=['*']      # always give the option to read in all targets
        visit_list=[]
        # the beamline directory could be a the real directory or
        # a directory where the visits are linked into
        if len(self.beamline_directory.split('/')) and \
            self.beamline_directory.split('/')[1]=='dls' and self.beamline_directory.split('/')[3]=='data' \
            and not 'labxchem' in self.beamline_directory:
            visit_list.append(self.beamline_directory)
        else:
            for dir in glob.glob(self.beamline_directory+'/*'):
                visit_list.append(os.path.realpath(dir))
        for visit in visit_list:
            for target in glob.glob(os.path.join(visit,'processed','*')):
                if target[target.rfind('/')+1:] not in ['results','README-log','edna-latest.html']:
                    if target[target.rfind('/')+1:] not in target_list:
                        target_list.append(target[target.rfind('/')+1:])
        return target_list,visit_list




    def start_GUI(self):


        # GUI setup
        self.window=QtGui.QWidget()
        self.window.setGeometry(0,0, 800,600)
        self.window.setWindowTitle("XChemExplorer")
#        self.center_main_window()

        # Menu Widget
        load=QtGui.QAction("Open Config File", self.window)
        load.setShortcut('Ctrl+O')
        load.triggered.connect(self.open_config_file)
        save=QtGui.QAction("Save Config File", self.window)
        save.setShortcut('Ctrl+S')
        save.triggered.connect(self.save_config_file)
        quit=QtGui.QAction("Quit", self.window)
        quit.setShortcut('Ctrl+Q')
        quit.triggered.connect(QtGui.qApp.quit)

        menu_bar = QtGui.QMenuBar()
        file = menu_bar.addMenu("&File")
#        settings = menu_bar.addMenu("&Settings")
        help = menu_bar.addMenu("&Help")

        file.addAction(load)
        file.addAction(save)
        file.addAction(quit)

        ######################################################################################
        # Tab widget
        tab_widget = QtGui.QTabWidget()
        tab_list = [    'Settings',
                        'Data Source',
                        'Overview',
                        'DLS @ Data Collection',
                        'DLS @ Summary',
                        'Initial Model',
                        'PANDDAs',
                        'Summary & Refine',
                        'Crystal Form'  ]
        self.tab_dict={}
        for page in tab_list:
            tab=QtGui.QWidget()
            vbox=QtGui.QVBoxLayout(tab)
            tab_widget.addTab(tab,page)
            self.tab_dict[page]=[tab,vbox]

        ######################################################################################
        # Data Source Tab
        self.data_source_columns_to_display=[   'Sample ID',
                                                'Compound ID',
                                                'Smiles'           ]
        self.mounted_crystal_table=QtGui.QTableWidget()
        self.mounted_crystal_table.setSortingEnabled(True)
#        self.mounted_crystal_table.setColumnWidth(0,250)
        self.mounted_crystal_table.resizeColumnsToContents()
        self.mounted_crystals_vbox_for_table=QtGui.QVBoxLayout()
        self.tab_dict['Data Source'][1].addLayout(self.mounted_crystals_vbox_for_table)
        self.mounted_crystals_vbox_for_table.addWidget(self.mounted_crystal_table)
        mounted_crystals_button_hbox=QtGui.QHBoxLayout()
        get_mounted_crystals_button=QtGui.QPushButton("Load Samples\nFrom Datasource")
        get_mounted_crystals_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(get_mounted_crystals_button)
        save_mounted_crystals_button=QtGui.QPushButton("Save Samples\nTo Datasource")
        save_mounted_crystals_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(save_mounted_crystals_button)
        create_png_of_soaked_compound_button=QtGui.QPushButton("Create PDB/CIF/PNG\nfiles of Compound")
        create_png_of_soaked_compound_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(create_png_of_soaked_compound_button)
        create_new_data_source_button=QtGui.QPushButton("Create New Data\nSource (SQLite)")
        create_new_data_source_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(create_new_data_source_button)
        import_csv_into_data_source_button=QtGui.QPushButton("Import CSV file\ninto Data Source")
        import_csv_into_data_source_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(import_csv_into_data_source_button)
        export_csv_from_data_source_button=QtGui.QPushButton("Export CSV file\nfrom Data Source")
        export_csv_from_data_source_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(export_csv_from_data_source_button)
        select_data_source_columns_to_display_button=QtGui.QPushButton("Select Columns")
        select_data_source_columns_to_display_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(select_data_source_columns_to_display_button)
        update_data_source_button=QtGui.QPushButton("Update\nDatasource")
        update_data_source_button.clicked.connect(self.button_clicked)
        mounted_crystals_button_hbox.addWidget(update_data_source_button)
        self.tab_dict['Data Source'][1].addLayout(mounted_crystals_button_hbox)

        ######################################################################################
        # DLS @ Data Collection Tab
        self.data_collection_vbox_for_table=QtGui.QVBoxLayout()
        self.tab_dict['DLS @ Data Collection'][1].addLayout(self.data_collection_vbox_for_table)
        data_collection_button_hbox=QtGui.QHBoxLayout()
        get_data_collection_button=QtGui.QPushButton("Get New Results from Autoprocessing")
        get_data_collection_button.clicked.connect(self.button_clicked)
        data_collection_button_hbox.addWidget(get_data_collection_button)
        write_files_button=QtGui.QPushButton("Save Files from Autoprocessing in 'inital_model' Folder")
        write_files_button.clicked.connect(self.button_clicked)
        data_collection_button_hbox.addWidget(write_files_button)
        self.target_selection_combobox = QtGui.QComboBox()
        self.populate_target_selection_combobox(self.target_selection_combobox)
        self.target_selection_combobox.activated[str].connect(self.target_selection_combobox_activated)
        data_collection_button_hbox.addWidget(self.target_selection_combobox)
        read_pickle_file_button=QtGui.QPushButton("Read Pickle File")
        read_pickle_file_button.clicked.connect(self.button_clicked)
        data_collection_button_hbox.addWidget(read_pickle_file_button)
        self.tab_dict['DLS @ Data Collection'][1].addLayout(data_collection_button_hbox)
        self.target=str(self.target_selection_combobox.currentText())

        ######################################################################################
        # Overview Tab
        self.data_collection_vbox_for_overview=QtGui.QVBoxLayout()
        self.overview_figure, self.overview_axes = plt.subplots(nrows=2, ncols=2)
        self.overview_canvas = FigureCanvas(self.overview_figure)
        self.update_overview()
        self.data_collection_vbox_for_overview.addWidget(self.overview_canvas)
        show_overview_button=QtGui.QPushButton("Show Overview")
        show_overview_button.clicked.connect(self.button_clicked)
        self.data_collection_vbox_for_overview.addWidget(show_overview_button)
        self.tab_dict['Overview'][1].addLayout(self.data_collection_vbox_for_overview)

        ######################################################################################
        # DLS @ Summary
        data_collection_summary_list=[]
        self.data_collection_summary_column_name=[      'Sample ID',
                                                        'Puck',
                                                        'Position',
                                                        'Date',
                                                        'img1',
                                                        'img2',
                                                        'img3',
                                                        'img4',
                                                        'Program',
                                                        'Space\nGroup',
                                                        'Dataset\nOutcome',
                                                        'Resolution\nOverall',
                                                        'Rmerge\nInner Shell',
                                                        'Mn(I/sig(I))\nOuter Shell',
                                                        'Completeness\nOverall',
                                                        'Show Diffraction\nImage'
                                                        ]

        data_collection_summary_list.append(['']*len(self.data_collection_summary_column_name))
        self.data_collection_summary_table=QtGui.QTableWidget()
        self.data_collection_summary_table.setRowCount(len(data_collection_summary_list))
#        self.data_collection_summary_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.data_collection_summary_table.setColumnCount(len(self.data_collection_summary_column_name))
        self.data_collection_summary_table.setSortingEnabled(True)
        for row,line in enumerate(data_collection_summary_list):
            for column,item in enumerate(line):
                cell_text=QtGui.QTableWidgetItem()
                cell_text.setText(str(item))
                cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                self.data_collection_summary_table.setItem(row, column, cell_text)
        self.data_collection_summary_table.setHorizontalHeaderLabels(self.data_collection_summary_column_name)
        self.data_collection_summarys_vbox_for_table=QtGui.QVBoxLayout()
        self.tab_dict['DLS @ Summary'][1].addLayout(self.data_collection_summarys_vbox_for_table)
        self.data_collection_summarys_vbox_for_table.addWidget(self.data_collection_summary_table)


        ######################################################################################
        # Initial Model Tab
        initial_model_checkbutton_hbox=QtGui.QHBoxLayout()
        select_sample_for_dimple = QtGui.QCheckBox('(de-)select all samples for DIMPLE')
        select_sample_for_dimple.toggle()
        select_sample_for_dimple.setChecked(False)
        select_sample_for_dimple.stateChanged.connect(self.set_run_dimple_flag)
        initial_model_checkbutton_hbox.addWidget(select_sample_for_dimple)
        self.tab_dict['Initial Model'][1].addLayout(initial_model_checkbutton_hbox)
        self.initial_model_vbox_for_table=QtGui.QVBoxLayout()
        self.initial_model_column_name = [  'SampleID',
                                            'Run\nDimple',
                                            'Resolution',
                                            'Rcryst',
                                            'Rfree',
                                            'Space Group\nautoprocessing',
                                            'Space Group\nreference',
                                            'Difference\nUnit Cell Volume (%)',
                                            'Reference File',
                                            'Unit Cell\nautoprocessing',
                                            'Unit Cell\nreference'  ]
        self.initial_model_table=QtGui.QTableWidget()
        self.initial_model_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.initial_model_table.setSortingEnabled(True)
        self.initial_model_table.setHorizontalHeaderLabels(self.initial_model_column_name)
        self.initial_model_vbox_for_table.addWidget(self.initial_model_table)
        self.tab_dict['Initial Model'][1].addLayout(self.initial_model_vbox_for_table)
        initial_model_button_hbox=QtGui.QHBoxLayout()
        get_initial_model_button=QtGui.QPushButton("Check for inital Refinement")
        get_initial_model_button.clicked.connect(self.button_clicked)
        initial_model_button_hbox.addWidget(get_initial_model_button)
        run_dimple_button=QtGui.QPushButton("Run Dimple")
        run_dimple_button.clicked.connect(self.button_clicked)
        initial_model_button_hbox.addWidget(run_dimple_button)
        refresh_inital_model_button=QtGui.QPushButton("Refresh")
        refresh_inital_model_button.clicked.connect(self.button_clicked)
        initial_model_button_hbox.addWidget(refresh_inital_model_button)
        self.reference_file_list=self.get_reference_file_list(' ')
        self.reference_file_selection_combobox = QtGui.QComboBox()
        self.populate_reference_combobox(self.reference_file_selection_combobox)
        initial_model_button_hbox.addWidget(self.reference_file_selection_combobox)
        set_new_reference_button=QtGui.QPushButton("Set New Reference (if applicable)")
        set_new_reference_button.clicked.connect(self.button_clicked)
        initial_model_button_hbox.addWidget(set_new_reference_button)
#        run_panddas_button=QtGui.QPushButton("Run PANDDAs")
#        run_panddas_button.clicked.connect(self.button_clicked)
#        initial_model_button_hbox.addWidget(run_panddas_button)
        self.tab_dict['Initial Model'][1].addLayout(initial_model_button_hbox)

        ######################################################################################
        # Summary & Refine Tab
        # prgress table
        # Sample ID
        # tag
        # compound
        # dataset outcome
        # space group
        # resolution
        # R/Rfree
        # PANDDAs/ Averaging
        # Refinement outcome
        # ligand CC
        self.summary_vbox_for_table=QtGui.QVBoxLayout()
        self.summary_column_name=[ 'Sample ID',
                                    'Compound ID',
#                                    'Compound\nImage',
                                    'DataCollection\nOutcome',
                                    'DataProcessing\nSpaceGroup',
                                    'DataProcessing\nResolutionHigh',
                                    'Refinement\nOutcome',
                                    'Refinement\nRcryst',
                                    'Refinement\nRfree' ]
        self.summary_table=QtGui.QTableWidget()
        self.summary_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.summary_table.setSortingEnabled(True)
        self.summary_table.setHorizontalHeaderLabels(self.summary_column_name)
        self.summary_vbox_for_table.addWidget(self.summary_table)
        self.tab_dict['Summary & Refine'][1].addLayout(self.summary_vbox_for_table)
        summary_button_hbox=QtGui.QHBoxLayout()
        load_all_samples_button=QtGui.QPushButton("Load All Samples")
        load_all_samples_button.clicked.connect(self.button_clicked)
        summary_button_hbox.addWidget(load_all_samples_button)
        refresh_all_samples_button=QtGui.QPushButton("Refresh All Samples")
        refresh_all_samples_button.clicked.connect(self.button_clicked)
        summary_button_hbox.addWidget(refresh_all_samples_button)
        open_cootl_button=QtGui.QPushButton("Open COOT")
        open_cootl_button.clicked.connect(self.button_clicked)
        summary_button_hbox.addWidget(open_cootl_button)
        self.tab_dict['Summary & Refine'][1].addLayout(summary_button_hbox)


        ######################################################################################
        # PANDDAs Tab

        self.panddas_results_vbox=QtGui.QVBoxLayout()
        self.tab_dict['PANDDAs'][1].addLayout(self.panddas_results_vbox)


        pandda_tab_widget = QtGui.QTabWidget()
        pandda_tab_list = [ 'pandda.analyse',
                            'Dataset Summary',
                            'Results Summary',
                            'Inspect Summary'  ]
        self.pandda_tab_dict={}
        for page in pandda_tab_list:
            tab=QtGui.QWidget()
            vbox=QtGui.QVBoxLayout(tab)
            pandda_tab_widget.addTab(tab,page)
            self.pandda_tab_dict[page]=[tab,vbox]

        self.pandda_analyse_hbox=QtGui.QHBoxLayout()
        self.pandda_tab_dict['pandda.analyse'][1].addLayout(self.pandda_analyse_hbox)
        # left hand side: table with information about available datasets
        self.pandda_column_name = [ 'Sample ID',
                                    'Crystal Form\nName',
                                    'Dimple\nResolution High',
                                    'Dimple\nRcryst',
                                    'Dimple\nRfree' ]
        self.pandda_analyse_data_table=QtGui.QTableWidget()
        self.pandda_analyse_data_table.setSortingEnabled(True)
        self.pandda_analyse_data_table.resizeColumnsToContents()
        self.populate_pandda_analyse_input_table('use all datasets')
        self.pandda_analyse_hbox.addWidget(self.pandda_analyse_data_table)
        # right hand side: input parameters for PANDDAs run
        self.pandda_analyse_input_params_vbox=QtGui.QVBoxLayout()

        self.pandda_input_data_dir_label=QtGui.QLabel('data directory')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_input_data_dir_label)
        self.pandda_input_data_dir_entry = QtGui.QLineEdit()
        self.pandda_input_data_dir_entry.setText(os.path.join(self.initial_model_directory,'*','Dimple','dimple'))
        self.pandda_input_data_dir_entry.setFixedWidth(400)
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_input_data_dir_entry)

        self.pandda_output_dir_label=QtGui.QLabel('output directory')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_output_dir_label)
        self.pandda_output_data_dir_entry = QtGui.QLineEdit()
        self.pandda_output_data_dir_entry.setText(self.panddas_directory)
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_output_data_dir_entry)

        # qstat or local machine
        self.pandda_submission_mode_label=QtGui.QLabel('submit')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_submission_mode_label)
        self.pandda_submission_mode_selection_combobox = QtGui.QComboBox()
        self.pandda_submission_mode_selection_combobox.addItem('local machine')
        if self.external_software['qsub']:
            self.pandda_submission_mode_selection_combobox.addItem('qsub')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_submission_mode_selection_combobox)

        self.pandda_nproc_label=QtGui.QLabel('number of processors')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_nproc_label)
        self.pandda_nproc=multiprocessing.cpu_count()-1
        self.pandda_nproc_entry = QtGui.QLineEdit()
        self.pandda_nproc_entry.setText(str(self.pandda_nproc).replace(' ',''))
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_nproc_entry)

        # run pandda on specific crystalform only
        self.pandda_analyse_crystal_from_label=QtGui.QLabel('Use Specific Crystal Form Only')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_analyse_crystal_from_label)
        self.pandda_analyse_crystal_from_selection_combobox = QtGui.QComboBox()
        self.pandda_analyse_crystal_from_selection_combobox.currentIndexChanged.connect(self.pandda_analyse_crystal_from_selection_combobox_changed)
        self.update_pandda_crystal_from_combobox()
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_analyse_crystal_from_selection_combobox)

        # minimum number of datasets
        self.pandda_min_build_dataset_label=QtGui.QLabel('min_build_datasets')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_min_build_dataset_label)
        self.pandda_min_build_dataset_entry = QtGui.QLineEdit()
        self.pandda_min_build_dataset_entry.setText('40')
        self.pandda_analyse_input_params_vbox.addWidget(self.pandda_min_build_dataset_entry)


        self.pandda_analyse_input_params_vbox.addStretch(1)


        # green 'Run Pandda' button (which is red when pandda run in progress
        self.run_panddas_button=QtGui.QPushButton("Run PANDDAs")
        self.run_panddas_button.clicked.connect(self.button_clicked)
        self.run_panddas_button.setFixedWidth(200)
        self.run_panddas_button.setFixedHeight(100)
        self.color_run_panddas_button()
        self.pandda_analyse_input_params_vbox.addWidget(self.run_panddas_button)

        self.pandda_analyse_hbox.addLayout(self.pandda_analyse_input_params_vbox)

        #######################################################
        # next three blocks display html documents created by pandda.analyse
        self.pandda_initial_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_initial.html')
        self.pandda_analyse_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_analyse.html')
        self.pandda_inspect_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_inspect.html')

        self.pandda_initial_html = QtWebKit.QWebView()
        self.pandda_tab_dict['Dataset Summary'][1].addWidget(self.pandda_initial_html)
        self.pandda_initial_html.load(QtCore.QUrl(self.pandda_initial_html_file))
        self.pandda_initial_html.show()

        self.pandda_analyse_html = QtWebKit.QWebView()
        self.pandda_tab_dict['Results Summary'][1].addWidget(self.pandda_analyse_html)
        self.pandda_analyse_html.load(QtCore.QUrl(self.pandda_analyse_html_file))
        self.pandda_analyse_html.show()

        self.pandda_inspect_html = QtWebKit.QWebView()
        self.pandda_tab_dict['Inspect Summary'][1].addWidget(self.pandda_inspect_html)
        self.pandda_inspect_html.load(QtCore.QUrl(self.pandda_inspect_html_file))
        self.pandda_inspect_html.show()


#        self.pandda_analyse_html = QtWebKit.QWebView()
#        self.pandda_inspect_html = QtWebKit.QWebView()

        self.panddas_results_vbox.addWidget(pandda_tab_widget)


        panddas_button_hbox=QtGui.QHBoxLayout()
        show_panddas_results=QtGui.QPushButton("Show PANDDAs Results")
        show_panddas_results.clicked.connect(self.button_clicked)
        panddas_button_hbox.addWidget(show_panddas_results)
#        reload_panddas_results=QtGui.QPushButton("Reload PANDDAs Results")
#        reload_panddas_results.clicked.connect(self.button_clicked)
#        panddas_button_hbox.addWidget(reload_panddas_results)
        launch_panddas_inspect=QtGui.QPushButton("Launch pandda.inspect")
        launch_panddas_inspect.clicked.connect(self.button_clicked)
        panddas_button_hbox.addWidget(launch_panddas_inspect)
        export_panddas_inspect=QtGui.QPushButton("Export PANDDA Models")
        export_panddas_inspect.clicked.connect(self.button_clicked)
        panddas_button_hbox.addWidget(export_panddas_inspect)
        self.tab_dict['PANDDAs'][1].addLayout(panddas_button_hbox)


        ######################################################################################
        # Crystal Form Tab
        self.vbox_for_crystal_form_table=QtGui.QVBoxLayout()
#        self.vbox_for_crystal_form_table.addStretch(1)
        self.crystal_form_column_name=[ 'Crystal Form\nName',
                                        'Space\nGroup',
                                        'Point\nGroup',
                                        'a',
                                        'b',
                                        'c',
                                        'alpha',
                                        'beta',
                                        'gamma',
                                        'Crystal Form\nVolume'  ]
        self.crystal_form_table=QtGui.QTableWidget()
        self.crystal_form_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.crystal_form_table.setSortingEnabled(True)
        self.crystal_form_table.setHorizontalHeaderLabels(self.crystal_form_column_name)
        self.vbox_for_crystal_form_table.addWidget(self.crystal_form_table)
        self.tab_dict['Crystal Form'][1].addLayout(self.vbox_for_crystal_form_table)

#        self.vbox_for_crystal_form_table.addStretch(1)

        crystal_form_button_hbox=QtGui.QHBoxLayout()
        load_all_crystal_form_button=QtGui.QPushButton("Load Crystal Forms From Datasource")
        load_all_crystal_form_button.clicked.connect(self.button_clicked)
        crystal_form_button_hbox.addWidget(load_all_crystal_form_button)
        suggest_crystal_form_button=QtGui.QPushButton("Suggest Additional Crystal Forms")
        suggest_crystal_form_button.clicked.connect(self.button_clicked)
        crystal_form_button_hbox.addWidget(suggest_crystal_form_button)
        assign_crystal_form_button=QtGui.QPushButton("Assign Crystal Forms To Samples")
        assign_crystal_form_button.clicked.connect(self.button_clicked)
        crystal_form_button_hbox.addWidget(assign_crystal_form_button)
        self.tab_dict['Crystal Form'][1].addLayout(crystal_form_button_hbox)


        ######################################################################################
        # Settings Tab
        self.data_collection_vbox_for_settings=QtGui.QVBoxLayout()
        self.tab_dict['Settings'][1].addLayout(self.data_collection_vbox_for_settings)
#        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('Project Directory:'))
#        settings_hbox_project_directory=QtGui.QHBoxLayout()
#        self.project_directory_label=QtGui.QLabel(self.project_directory)
#        settings_hbox_project_directory.addWidget(self.project_directory_label)
#        settings_buttoon_project_directory=QtGui.QPushButton('Select Project Directory')
#        settings_buttoon_project_directory.clicked.connect(self.settings_button_clicked)
#        settings_hbox_project_directory.addWidget(settings_buttoon_project_directory)
#        self.data_collection_vbox_for_settings.addLayout(settings_hbox_project_directory)
        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nInitial Model Directory:'))
        settings_hbox_initial_model_directory=QtGui.QHBoxLayout()
        self.initial_model_directory_label=QtGui.QLabel(self.initial_model_directory)
        settings_hbox_initial_model_directory.addWidget(self.initial_model_directory_label)
        settings_buttoon_initial_model_directory=QtGui.QPushButton('Select Initial Model Directory')
        settings_buttoon_initial_model_directory.clicked.connect(self.settings_button_clicked)
        settings_hbox_initial_model_directory.addWidget(settings_buttoon_initial_model_directory)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_initial_model_directory)

        settings_hbox_filename_root=QtGui.QHBoxLayout()
        self.filename_root_label=QtGui.QLabel('filename root:')
        settings_hbox_filename_root.addWidget(self.filename_root_label)
        settings_hbox_filename_root.addStretch(1)
        self.filename_root_input = QtGui.QLineEdit()
        self.filename_root_input.setFixedWidth(400)
        self.filename_root_input.setText(str(self.filename_root))
        self.filename_root_input.textChanged[str].connect(self.change_filename_root)
        settings_hbox_filename_root.addWidget(self.filename_root_input)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_filename_root)

        settings_hbox_adjust_allowed_unit_cell_difference=QtGui.QHBoxLayout()
        self.adjust_allowed_unit_cell_difference_label=QtGui.QLabel('Max. Allowed Unit Cell Difference between Reference and Target (%):')
        settings_hbox_adjust_allowed_unit_cell_difference.addWidget(self.adjust_allowed_unit_cell_difference_label)
        settings_hbox_adjust_allowed_unit_cell_difference.addStretch(1)
        self.adjust_allowed_unit_cell_difference = QtGui.QLineEdit()
        self.adjust_allowed_unit_cell_difference.setFixedWidth(200)
        self.adjust_allowed_unit_cell_difference.setText(str(self.allowed_unitcell_difference_percent))
        self.adjust_allowed_unit_cell_difference.textChanged[str].connect(self.change_allowed_unitcell_difference_percent)
        settings_hbox_adjust_allowed_unit_cell_difference.addWidget(self.adjust_allowed_unit_cell_difference)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_adjust_allowed_unit_cell_difference)

#        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nRefine Model Directory:'))
#        settings_hbox_refine_model_directory=QtGui.QHBoxLayout()
#        self.refine_model_directory_label=QtGui.QLabel(self.refine_model_directory)
#        settings_hbox_refine_model_directory.addWidget(self.refine_model_directory_label)
#        settings_buttoon_refine_model_directory=QtGui.QPushButton('Select Refine Model Directory')
#        settings_buttoon_refine_model_directory.clicked.connect(self.settings_button_clicked)
#        settings_hbox_refine_model_directory.addWidget(settings_buttoon_refine_model_directory)
#        self.data_collection_vbox_for_settings.addLayout(settings_hbox_refine_model_directory)

        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nReference Structure Directory:'))
        settings_hbox_reference_directory=QtGui.QHBoxLayout()
        self.reference_directory_label=QtGui.QLabel(self.reference_directory)
        settings_hbox_reference_directory.addWidget(self.reference_directory_label)
        settings_buttoon_reference_directory=QtGui.QPushButton('Select Reference Structure Directory')
        settings_buttoon_reference_directory.clicked.connect(self.settings_button_clicked)
        settings_hbox_reference_directory.addWidget(settings_buttoon_reference_directory)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_reference_directory)
        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nData Source:'))
        settings_hbox_database_directory=QtGui.QHBoxLayout()

        self.database_directory_label=QtGui.QLabel(self.database_directory)
        settings_hbox_database_directory.addWidget(self.database_directory_label)
        settings_buttoon_database_directory=QtGui.QPushButton('Select Data Source Directory')
        settings_buttoon_database_directory.clicked.connect(self.settings_button_clicked)
        settings_hbox_database_directory.addWidget(settings_buttoon_database_directory)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_database_directory)

        settings_hbox_data_source_file=QtGui.QHBoxLayout()
        self.data_source_file_label=QtGui.QLabel(self.data_source_file)
        settings_hbox_data_source_file.addWidget(self.data_source_file_label)
        settings_buttoon_data_source_file=QtGui.QPushButton('Select Data Source File')
        settings_buttoon_data_source_file.clicked.connect(self.settings_button_clicked)
        settings_hbox_data_source_file.addWidget(settings_buttoon_data_source_file)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_data_source_file)

        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nBeamline Directory:'))
        settings_hbox_beamline_directory=QtGui.QHBoxLayout()
        self.beamline_directory_label=QtGui.QLabel(self.beamline_directory)
        settings_hbox_beamline_directory.addWidget(self.beamline_directory_label)
        settings_buttoon_beamline_directory=QtGui.QPushButton('Select Beamline Directory')
        settings_buttoon_beamline_directory.clicked.connect(self.settings_button_clicked)
        settings_hbox_beamline_directory.addWidget(settings_buttoon_beamline_directory)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_beamline_directory)

        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nCCP4_SCR Directory:'))
        settings_hbox_ccp4_scratch_directory=QtGui.QHBoxLayout()
        self.ccp4_scratch_directory_label=QtGui.QLabel(self.ccp4_scratch_directory)
        settings_hbox_ccp4_scratch_directory.addWidget(self.ccp4_scratch_directory_label)
        settings_buttoon_ccp4_scratch_directory=QtGui.QPushButton('Select CCP4_SCR Directory')
        settings_buttoon_ccp4_scratch_directory.clicked.connect(self.settings_button_clicked)
        settings_hbox_ccp4_scratch_directory.addWidget(settings_buttoon_ccp4_scratch_directory)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_ccp4_scratch_directory)

        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nPANDDAs directory:'))
        settings_hbox_panddas_directory=QtGui.QHBoxLayout()
        self.panddas_directory_label=QtGui.QLabel(self.panddas_directory)
        settings_hbox_panddas_directory.addWidget(self.panddas_directory_label)
        settings_button_panddas_directory=QtGui.QPushButton('Select PANNDAs Directory')
        settings_button_panddas_directory.clicked.connect(self.settings_button_clicked)
        settings_hbox_panddas_directory.addWidget(settings_button_panddas_directory)
        self.data_collection_vbox_for_settings.addLayout(settings_hbox_panddas_directory)

#        self.data_collection_vbox_for_settings.addWidget(QtGui.QLabel('\n\nSites of Interest:'))
#        self.sites_of_interest_input = QtGui.QTextEdit()
#        self.sites_of_interest_input.setFixedWidth(400)
#        self.data_collection_vbox_for_settings.addWidget(self.sites_of_interest_input)


#        self.data_collection_vbox_for_settings.addStretch(1)
        ######################################################################################

        self.status_bar=QtGui.QStatusBar()
        self.progress_bar=QtGui.QProgressBar()
        self.progress_bar.setMaximum(100)
        hbox_status=QtGui.QHBoxLayout()
        hbox_status.addWidget(self.status_bar)
        hbox_status.addWidget(self.progress_bar)

        vbox_main = QtGui.QVBoxLayout()
        vbox_main.addWidget(menu_bar)
        vbox_main.addWidget(tab_widget)
        vbox_main.addLayout(hbox_status)

        self.window.setLayout(vbox_main)

        self.status_bar.showMessage('Ready')
#        self.timer = QtCore.QBasicTimer()
#        self.window.showMaximized()
        self.window.show()

    def color_run_panddas_button(self):
        if os.path.isfile(os.path.join(self.panddas_directory,'PANDDA_RUN_IN_PROGRESS')):
            self.run_panddas_button.setStyleSheet("background-color: red")
        else:
            self.run_panddas_button.setStyleSheet("background-color: green")

    def update_overview(self):
        if os.path.isfile(self.settings['data_source']):
            sqlite_query = ('Select '
                            'CrystalName,DataCollectionOutcome,RefinementOutcome,DataProcessingResolutionHigh,RefinementRfree '
                            'FROM mainTable')
            query=XChemDB.data_source(self.settings['data_source']).execute_statement(sqlite_query)
            Rfree_present=[]
            Rfree_missing=[]
            Resolution_present=[]
            Resolution_missing=[]
            data_collection_outcome={}
            refinement_outcome={}


            for item in query:

                if not str(item[1]).replace('Failed - ','') in data_collection_outcome:
                    if str(item[1])=='None':
                        data_collection_outcome['pending']=1
                    else:
                        data_collection_outcome[str(item[1]).replace('Failed - ','')]=1
                else:
                    if str(item[1])=='None':
                        data_collection_outcome['pending']+=1
                    else:
                        data_collection_outcome[str(item[1]).replace('Failed - ','')]+=1

                if not str(item[2]) in refinement_outcome:
                    if str(item[2]) != 'None':
                        refinement_outcome[str(item[2])]=1
                else:
                    refinement_outcome[str(item[2])]+=1

                if str(item[3])=='None':
                    Resolution_missing.append(0)
                else:
#                    if isinstance(float(item[3]),float):
                    try:
                        Resolution_present.append(float(item[3]))
                    except ValueError:
                        pass

                if str(item[4])=='None':
                    Rfree_missing.append(0)
                else:
                    try:
                        Rfree_present.append(float(item[4]))
                    except ValueError:
                        pass

            ax0, ax1, ax2, ax3 = self.overview_axes.flat

            ax0.set_title('Data Collection - Outcome')
            ax0.set_ylabel("Frequency")
            outcome=[]
            frequency=[]
            for key in data_collection_outcome:
                outcome.append(key)
                frequency.append(data_collection_outcome[key])
            y_pos = np.arange(len(outcome))
            try:
                ax0.bar(y_pos, frequency, width=0.15)
            except ValueError:
                pass
            ax0.set_xticks(np.arange(len(outcome)) + 0.15/2)
            ax0.set_xticklabels(outcome, rotation=0)

            ax1.set_title('Data Collection - Resolution')
            try:
                ax1.hist((Resolution_missing, Resolution_present), bins=20, color=("red", "green"), label=("missing","analysed"))
            except ValueError:
                pass
            ax1.set_xlabel("Resolution")
            ax1.legend(prop={'size': 10})

            ax2.set_title('Map Analysis - Outcome')
            ax2.set_ylabel("Frequency")
            outcome=[]
            frequency=[]
            for key in refinement_outcome:
                outcome.append(key)
                frequency.append(refinement_outcome[key])
            y_pos = np.arange(len(outcome))
            try:
                ax2.bar(y_pos, frequency, width=0.15)
            except ValueError:
                pass
            ax2.set_xticks(np.arange(len(outcome)) + 0.15/2)
            ax2.set_xticklabels(outcome, rotation=0)

            ax3.set_title('Refinement - Rfree')
            try:
                ax3.hist((Rfree_missing, Rfree_present), bins=20, color=("red", "green"), label=("missing","analysed"))
            except ValueError:
                pass
            ax3.set_xlabel("Rfree")
            ax3.legend(prop={'size': 10})


#            ax = self.overview_figure.add_subplot(111)
#            ax.hist((Rfree_missing, Rfree_present), bins=20, color=("red", "green"), label=("missing","analysed"))
#            ax.legend(prop={'size': 10})
#            ax.set_title('bars with legend')
#            ax.set_xlabel("Rfree")
#            ax.set_ylabel("Frequency")
        self.overview_canvas.draw()

    def update_pandda_crystal_from_combobox(self):
        self.pandda_analyse_crystal_from_selection_combobox.clear()
        self.pandda_analyse_crystal_from_selection_combobox.addItem('use all datasets')
        if os.path.isfile(os.path.join(self.database_directory,self.data_source_file)):
            self.load_crystal_form_from_datasource()
            if self.xtalform_dict != {}:
                for key in self.xtalform_dict:
                    self.pandda_analyse_crystal_from_selection_combobox.addItem(key)


    def populate_reference_combobox(self,combobox):
        combobox.clear()
        for reference_file in self.reference_file_list:
            combobox.addItem(reference_file[0])

    def populate_target_selection_combobox(self,combobox):
        combobox.clear()
        for target in self.target_list:
            combobox.addItem(target)


    def open_config_file(self):
        file_name = QtGui.QFileDialog.getOpenFileName(self.window,'Open file', self.current_directory)

        try:
            pickled_settings = pickle.load(open(file_name,"rb"))
            if pickled_settings['beamline_directory'] != self.beamline_directory:
                self.beamline_directory=pickled_settings['beamline_directory']
                self.target_list,self.visit_list=self.get_target_and_visit_list()
                self.settings['beamline_directory']=self.beamline_directory
                self.populate_target_selection_combobox(self.target_selection_combobox)

            self.initial_model_directory=pickled_settings['initial_model_directory']
            self.settings['initial_model_directory']=self.initial_model_directory

            self.panddas_directory=pickled_settings['panddas_directory']
            self.settings['panddas_directory']=self.panddas_directory
            self.pandda_initial_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_initial.html')
            self.pandda_analyse_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_analyse.html')
            self.pandda_inspect_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_inspect.html')


            self.database_directory=pickled_settings['database_directory']
            self.settings['database_directory']=self.database_directory

            self.data_source_file=pickled_settings['data_source']
            if self.data_source_file != '':
                self.settings['data_source']=os.path.join(self.database_directory,self.data_source_file)
                # this is probably not necessary
                if os.path.isfile(self.settings['data_source']):
                    self.data_source_set=True
#                    XChemDB.data_source(self.settings['data_source']).create_missing_columns()
#                else:
#                    XChemDB.data_source(self.settings['data_source']).create_empty_data_source_file()
#                self.data_source_set=True

            self.ccp4_scratch_directory=pickled_settings['ccp4_scratch']
            self.settings['ccp4_scratch']=self.ccp4_scratch_directory

            self.allowed_unitcell_difference_percent=pickled_settings['unitcell_difference']

            reference_directory_temp=pickled_settings['reference_directory']
            if reference_directory_temp != self.reference_directory:
                self.reference_directory=reference_directory_temp
                self.settings['reference_directory']=self.reference_directory
                self.update_reference_files(' ')

#            self.project_directory_label.setText(self.project_directory)
            self.initial_model_directory_label.setText(self.initial_model_directory)
            self.panddas_directory_label.setText(self.panddas_directory)
#            self.refine_model_directory_label.setText(self.refine_model_directory)
            self.reference_directory_label.setText(self.reference_directory)
            self.database_directory_label.setText(self.database_directory)
            self.beamline_directory_label.setText(self.beamline_directory)
            self.data_source_file_label.setText(self.data_source_file)
            self.ccp4_scratch_directory_label.setText(self.ccp4_scratch_directory)
            self.adjust_allowed_unit_cell_difference.setText(str(self.allowed_unitcell_difference_percent))
            self.reference_file_list=self.get_reference_file_list(' ')


        except KeyError:
            self.update_status_bar('Sorry, this is not a XChemExplorer config file!')

    def save_config_file(self):
        file_name = QtGui.QFileDialog.getSaveFileName(self.window,'Save file', self.current_directory)
        pickle.dump(self.settings,open(file_name,'wb'))

    def update_reference_files(self,reference_root):
        self.reference_file_list=self.get_reference_file_list(reference_root)
        self.populate_reference_combobox(self.reference_file_selection_combobox)
        if self.initial_model_dimple_dict != {}:
            self.explorer_active=1
            update_datasource_only=False
            self.work_thread=XChemThread.read_intial_refinement_results(self.initial_model_directory,
                                                                        self.reference_file_list,
                                                                        os.path.join(self.database_directory,
                                                                                     self.data_source_file),
                                                                        self.allowed_unitcell_difference_percent,
                                                                        self.filename_root,
                                                                        update_datasource_only  )
            self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.connect(self.work_thread, QtCore.SIGNAL("create_initial_model_table"),self.create_initial_model_table)
            self.work_thread.start()

    def target_selection_combobox_activated(self,text):
        self.target=str(text)

    def center_main_window(self):
        screen = QtGui.QDesktopWidget().screenGeometry()
        size = self.window.geometry()
        self.window.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)

    def settings_button_clicked(self):
        if self.sender().text()=='Select Project Directory':
            self.project_directory = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            self.project_directory_label.setText(self.project_directory)
            self.settings['project_directory']=self.project_directory
        if self.sender().text()=='Select Initial Model Directory':
            self.initial_model_directory = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            self.initial_model_directory_label.setText(self.initial_model_directory)
            self.settings['initial_model_directory']=self.initial_model_directory
        if self.sender().text()=='Select Refine Model Directory':
            self.refine_model_directory = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            self.refine_model_directory_label.setText(self.refine_model_directory)
            self.settings['refine_model_directory']=self.refine_model_directory
        if self.sender().text()=='Select Reference Structure Directory':
            reference_directory_temp = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            if reference_directory_temp != self.reference_directory:
                self.reference_directory=reference_directory_temp
                self.update_reference_files(' ')
            self.reference_directory_label.setText(self.reference_directory)
            self.settings['reference_directory']=self.reference_directory
        if self.sender().text()=='Select Data Source Directory':
            self.database_directory = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            self.database_directory_label.setText(self.database_directory)
            self.settings['database_directory']=self.database_directory
        if self.sender().text()=='Select Data Source File':
            filepath=str(QtGui.QFileDialog.getOpenFileName(self.window,'Select File', self.database_directory))
            self.data_source_file =   filepath.split('/')[-1]
            self.database_directory = filepath[:filepath.rfind('/')]
            self.data_source_file_label.setText(self.data_source_file)
            self.database_directory_label.setText(str(self.database_directory))
            self.settings['database_directory']=self.database_directory
            self.settings['data_source']=os.path.join(self.database_directory,self.data_source_file)
            self.data_source_set=True
            XChemDB.data_source(self.settings['data_source']).create_missing_columns()
        if self.sender().text()=='Select Beamline Directory':
            dir_name = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            if dir_name != self.beamline_directory:
                self.beamline_directory=dir_name
                self.target_list,self.visit_list=self.get_target_and_visit_list()
                self.populate_target_selection_combobox(self.target_selection_combobox)
            self.beamline_directory_label.setText(self.beamline_directory)
            self.settings['beamline_directory']=self.beamline_directory
        if self.sender().text()=='Select CCP4_SCR Directory':
            self.ccp4_scratch_directory = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            self.ccp4_scratch_directory_label.setText(self.ccp4_scratch_directory)
            self.settings['ccp4_scratch']=self.ccp4_scratch_directory
        if self.sender().text()=='Select PANNDAs Directory':
            self.panddas_directory = str(QtGui.QFileDialog.getExistingDirectory(self.window, "Select Directory"))
            self.panddas_directory_label.setText(self.panddas_directory)
            self.pandda_output_data_dir_entry.setText(self.panddas_directory)
            print 'PANDDA',self.panddas_directory
            self.settings['panddas_directory']=self.panddas_directory
            self.pandda_initial_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_initial.html')
            self.pandda_analyse_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_analyse.html')
            self.pandda_inspect_html_file=os.path.join(self.panddas_directory,'results_summaries','pandda_inspect.html')



    def change_allowed_unitcell_difference_percent(self,text):
        self.allowed_unitcell_difference_percent=int(text)
        self.settings['unitcell_difference']=self.adjust_allowed_unit_cell_difference

    def change_filename_root(self,text):
        self.filename_root=str(text)
        self.settings['filename_root']=self.filename_root



    def button_clicked(self):

        if self.data_source_set==False:
            if self.sender().text()=="Create New Data\nSource (SQLite)":
                file_name = str(QtGui.QFileDialog.getSaveFileName(self.window,'Save file', self.database_directory))
                #make sure that the file always has .csv extension
                if file_name.rfind('.') != -1:
                    file_name=file_name[:file_name.rfind('.')]+'.sqlite'
                else:
                    file_name=file_name+'.sqlite'
                XChemDB.data_source(os.path.join(file_name)).create_empty_data_source_file()
                if self.data_source_file=='':
                    self.database_directory=file_name[:file_name.rfind('/')]
                    self.data_source_file=file_name[file_name.rfind('/')+1:]
                    self.data_source_file_label.setText(self.data_source_file)
                    self.database_directory_label.setText(str(self.database_directory))
                    self.settings['database_directory']=self.database_directory
                    self.settings['data_source']=self.data_source_file
                    self.data_source_set=True
            else:
                self.no_data_source_selected()
                pass



        if self.explorer_active==0 and self.data_source_set==True \
            and self.sender().text()=='Get New Results from Autoprocessing':
            self.work_thread=XChemThread.NEW_read_autoprocessing_results_from_disc(self.visit_list,
                                                                               self.target,
                                                                               self.reference_file_list,
                                                                               self.database_directory,
                                                                               self.data_collection_dict)
            self.explorer_active=1
            self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.connect(self.work_thread, QtCore.SIGNAL("create_widgets_for_autoprocessing_results"),
                                                     self.create_widgets_for_autoprocessing_results)
            self.work_thread.start()

        elif self.explorer_active==0 and self.data_source_set==True \
            and self.sender().text()=="Save Files from Autoprocessing in 'inital_model' Folder":
            self.work_thread=XChemThread.save_autoprocessing_results_to_disc(self.dataset_outcome_dict,
                                                                 self.data_collection_table_dict,
                                                                 self.data_collection_statistics_dict,
                                                                 self.database_directory,self.data_source_file,
                                                                 self.initial_model_directory)
            self.explorer_active=1
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.work_thread.start()

        elif self.explorer_active==0 and self.data_source_set==True \
            and self.sender().text()=="Read Pickle File":
            summary = pickle.load( open( os.path.join(self.database_directory,'data_collection_summary.pkl'), "rb" ) )
            self.create_widgets_for_autoprocessing_results(summary)

        elif self.explorer_active==0 \
            and self.sender().text()=="Load All Samples" or self.sender().text()=="Refresh All Samples":
            content=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).load_samples_from_data_source()
            header=content[0]
            data=content[1]
            self.populate_summary_table(header,data)

        elif (self.sender().text()=="Check for inital Refinement" and self.data_source_set==True) or \
             (self.sender().text()=="Update\nDatasource" and self.data_source_set==True):
            if self.sender().text()=="Update\nDatasource":
                update_datasource_only=True
            else:
                update_datasource_only=False
            # first check if there is already content in the table and if so
            # delete checkbox and combobox widgets
#            if self.initial_model_dimple_dict != {}:
#                for key in self.initial_model_dimple_dict:
#                    print key, self.initial_model_dimple_dict[key]

            self.explorer_active=1
            self.work_thread=XChemThread.read_intial_refinement_results(self.initial_model_directory,
                                                                        self.reference_file_list,
                                                                        os.path.join(self.database_directory,
                                                                                     self.data_source_file),
                                                                        self.allowed_unitcell_difference_percent,
                                                                        self.filename_root,
                                                                        update_datasource_only)
            self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.connect(self.work_thread, QtCore.SIGNAL("create_initial_model_table"),self.create_initial_model_table)
            self.work_thread.start()


        elif self.sender().text()=="Refresh":
            for key in self.initial_model_dimple_dict:
                print key, self.initial_model_dimple_dict[key]

        elif self.sender().text()=="Load Crystal Forms From Datasource":
            self.load_crystal_form_from_datasource()
            self.pandda_analyse_crystal_from_selection_combobox.clear()
            self.pandda_analyse_crystal_from_selection_combobox.addItem('all datasets')
            if self.xtalform_dict != {}:
                for key in self.xtalform_dict:
                    self.pandda_analyse_crystal_from_selection_combobox.addItem(key)
            self.update_xtalfrom_table(self.xtalform_dict)
            self.update_pandda_crystal_from_combobox()

        elif self.sender().text()=="Suggest Additional Crystal Forms" or \
             self.sender().text()=="Assign Crystal Forms To Samples":
            self.explorer_active=1
            if self.sender().text()=="Suggest Additional Crystal Forms":
                mode='suggest'
            if self.sender().text()=="Assign Crystal Forms To Samples":
                mode='assign'
                # allows user to change crystal from names
                allRows = self.crystal_form_table.rowCount()
                self.xtalform_dict={}
                for row in range(allRows):
                    crystal_form_name=str(self.crystal_form_table.item(row,0).text())      # this must be the case
                    self.xtalform_dict[crystal_form_name] = [
                            str(self.crystal_form_table.item(row,2).text()),
                            str(self.crystal_form_table.item(row,9).text()),
                            [   str(self.crystal_form_table.item(row,3).text()),
                                str(self.crystal_form_table.item(row,4).text()),
                                str(self.crystal_form_table.item(row,5).text()),
                                str(self.crystal_form_table.item(row,6).text()),
                                str(self.crystal_form_table.item(row,7).text()),
                                str(self.crystal_form_table.item(row,8).text()) ],
                            str(self.crystal_form_table.item(row,1).text())         ]


            self.work_thread=XChemThread.crystal_from(self.initial_model_directory,
                                                                        self.reference_file_list,
                                                                        os.path.join(self.database_directory,
                                                                                     self.data_source_file),
                                                                        self.filename_root,
                                                                        self.xtalform_dict,
                                                                        mode)
            self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.connect(self.work_thread, QtCore.SIGNAL("update_xtalfrom_table"),self.update_xtalfrom_table)
            self.work_thread.start()



        elif self.sender().text()=="Open COOT":
            if not self.coot_running:
                print 'starting coot'
                self.work_thread=XChemThread.start_COOT(self.settings)
                self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
                self.work_thread.start()

        elif self.sender().text()=="Run Dimple":
            self.explorer_active=1
            self.work_thread=XChemThread.run_dimple_on_selected_samples(self.settings,
                                                            self.initial_model_dimple_dict,
                                                            self.external_software,
                                                            self.ccp4_scratch_directory,
                                                            self.filename_root  )
            self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.work_thread.start()

        elif self.sender().text()=='Set New Reference (if applicable)':
            reference_root=str(self.reference_file_selection_combobox.currentText())
            self.update_reference_files(reference_root)


#                if self.initial_model_dimple_dict != {}
#                    for key in self.initial_model_dimple_dict:
#
#                    self.initial_model_dimple_dict[key][0].setChecked(True)
### thing that I forgot: if reference directory is chosen -> update reference file list
### if difference between old and new recalculate already if references appeared in initial_model table


        elif self.sender().text()=="Load Samples\nFrom Datasource":
            content=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).load_samples_from_data_source()
            header=content[0]
            data=content[1]
            self.populate_data_source_table(header,data)


        elif self.sender().text()=="Import CSV file\ninto Data Source":
            if self.data_source_file=='':
                self.update_status_bar('Please load a data source file first')
            else:
                file_name = QtGui.QFileDialog.getOpenFileName(self.window,'Open file', self.database_directory)
                XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).import_csv_file(file_name)

        elif self.sender().text()=="Export CSV file\nfrom Data Source":
            file_name = str(QtGui.QFileDialog.getSaveFileName(self.window,'Save file', self.database_directory))
            if file_name.rfind('.') != -1:
                file_name=file_name[:file_name.rfind('.')]+'.csv'
            else:
                file_name=file_name+'.csv'
            XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).export_to_csv_file(file_name)

        elif self.sender().text()=="Save Samples\nTo Datasource":
            # first translate all columns in table in SQLite tablenames
            columns_in_data_source=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).return_column_list()
            column_dict={}
            for item in self.data_source_columns_to_display:
                for column_name in columns_in_data_source:
                    if column_name[1]==item:
                        column_dict[item]=column_name[0]

            allRows = self.mounted_crystal_table.rowCount()
            for row in range(allRows):
                data_dict={}
                sampleID=str(self.mounted_crystal_table.item(row,0).text())      # this must be the case
                for i in range(1,len(self.data_source_columns_to_display)):
                    if self.mounted_crystal_table.item(row,i).text() != '':
                        headertext = str(self.mounted_crystal_table.horizontalHeaderItem(i).text())
                        column_to_update=column_dict[headertext]
                        data_dict[column_to_update]=str(self.mounted_crystal_table.item(row,i).text())
#                print sampleID,data_dict
                XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).update_data_source(sampleID,data_dict)


        elif self.sender().text()=="Select Columns":
            print 'hallo'
#            input_params = [os.path.join(self.database_directory,self.data_source_file),self.data_source_columns_to_display]
#            self.data_source_columns_to_display, ok = XChemDialogs.select_columns_to_show(input_params).return_selected_columns()
            self.data_source_columns_to_display, ok = XChemDialogs.select_columns_to_show(
                os.path.join(self.database_directory,self.data_source_file)).return_selected_columns()
            content=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).load_samples_from_data_source()
            header=content[0]
            data=content[1]
            self.populate_data_source_table(header,data)

#            date, time, ok = XChemDialogs.DateDialog.getDateTime()
#            print 'WERE HERE',str(date),str(time),str(ok)

        elif self.sender().text()=="Create PDB/CIF/PNG\nfiles of Compound":
            if helpers().pil_rdkit_exist()==False:
                QtGui.QMessageBox.warning(self.window, "Library Problem",
                                                       ('Cannot find PIL and RDKIT'),
                        QtGui.QMessageBox.Cancel, QtGui.QMessageBox.NoButton,
                        QtGui.QMessageBox.NoButton)
            else:
                columns_to_read=['Sample ID',
                                 'Compound ID',
                                 'Smiles']
                # it's a bit pointless now to search for the position of the columns,
                # but later I may want to give the user the option to change the column order
                headercount = self.mounted_crystal_table.columnCount()
                column_positions=[]
                for item in columns_to_read:
                    for x in range(headercount):
                        headertext = self.mounted_crystal_table.horizontalHeaderItem(x).text()
                        if headertext==item:
                            column_positions.append(x)
                            break
                allRows = self.mounted_crystal_table.rowCount()
                compound_list=[]
                for row in range(allRows):
                    if self.mounted_crystal_table.item(row,column_positions[2]).text() != '':
                        compound_list.append([str(self.mounted_crystal_table.item(row,column_positions[0]).text()),
                                              str(self.mounted_crystal_table.item(row,column_positions[1]).text()),
                                              str(self.mounted_crystal_table.item(row,column_positions[2]).text())] )
                if compound_list != []:
                    self.explorer_active=1
                    self.work_thread=XChemThread.create_png_and_cif_of_compound(self.external_software,
                                                                                self.initial_model_directory,
                                                                                compound_list)
                    self.connect(self.work_thread, QtCore.SIGNAL("update_progress_bar"), self.update_progress_bar)
                    self.connect(self.work_thread, QtCore.SIGNAL("update_status_bar(QString)"), self.update_status_bar)
                    self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
                    self.work_thread.start()


        elif str(self.sender().text()).startswith("Show Overview"):
            self.update_overview()

        elif str(self.sender().text()).startswith('Show: '):
            diffraction_image=''
            for key in self.albula_button_dict:
                if self.albula_button_dict[key][0]==self.sender():
                    diffraction_image=self.albula_button_dict[key][1]
            if not self.albula:
                self.albula = dectris.albula.openMainFrame()
            for frame in self.albula_subframes:
                frame.close()
            show_diffraction_image = self.albula.openSubFrame()
            show_diffraction_image.loadFile(os.path.join(diffraction_image))
            self.albula_subframes.append(show_diffraction_image)

        elif str(self.sender().text()).startswith("Run PANDDAs"):

            if str(self.pandda_analyse_crystal_from_selection_combobox.currentText())=='use all datasets':
                data_dir=str(self.pandda_input_data_dir_entry.text())
            else:
                # read table
                allRows = self.pandda_analyse_data_table.rowCount()
                tmp_dir=os.path.join(self.panddas_directory[:self.panddas_directory.rfind('/')],'tmp_pandda_'+str(self.pandda_analyse_crystal_from_selection_combobox.currentText()))
                if not os.path.isdir(tmp_dir):
                    os.mkdir(tmp_dir)
                data_dir=os.path.join(tmp_dir,'*')
                for row in range(allRows):
                    sample=str(self.pandda_analyse_data_table.item(row,0).text())
                    if os.path.isfile(os.path.join(str(self.pandda_input_data_dir_entry.text()).replace('*',sample),'final.pdb')    ):
                        if not os.path.isdir(os.path.join(tmp_dir,sample)):
                            os.mkdir(os.path.join(tmp_dir,sample))
                        os.chdir(os.path.join(tmp_dir,sample))
                        if not os.path.isfile('final.pdb'):
                            os.symlink(os.path.join(str(self.pandda_input_data_dir_entry.text()).replace('*',sample),'final.pdb'),'final.pdb')
                        if not os.path.isfile('final.mtz'):
                            os.symlink(os.path.join(str(self.pandda_input_data_dir_entry.text()).replace('*',sample),'final.mtz'),'final.mtz')
                # create softlinks to pseudo datadir
                # set new data_dir path

            pandda_params = {
                    'data_dir':             data_dir,
                    'out_dir':              str(self.pandda_output_data_dir_entry.text()),
                    'submit_mode':          str(self.pandda_submission_mode_selection_combobox.currentText()),
                    'nproc':                str(self.pandda_nproc_entry.text()),
                    'xtalform':             str(self.pandda_analyse_crystal_from_selection_combobox.currentText()),
                    'min_build_datasets':   str(self.pandda_min_build_dataset_entry.text())
                        }
            print pandda_params
            self.work_thread=XChemPANDDA.run_pandda_analyse(pandda_params)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.work_thread.start()

        elif str(self.sender().text()).startswith("Launch pandda.inspect"):
            pandda_params = {
                    'data_dir':         str(self.pandda_input_data_dir_entry.text()),
                    'out_dir':          str(self.pandda_output_data_dir_entry.text()),
                    'submit_mode':      str(self.pandda_submission_mode_selection_combobox.currentText()),
                    'nproc':            str(self.pandda_nproc_entry.text()),
                    'xtalform':         str(self.pandda_analyse_crystal_from_selection_combobox.currentText())
                        }
#            XChemPANDDA.PANDDAs(pandda_params).launch_pandda_inspect()
            print '==> XCE: starting pandda.inspect'
            self.work_thread=XChemThread.start_pandda_inspect(self.settings)
            self.connect(self.work_thread, QtCore.SIGNAL("finished()"), self.thread_finished)
            self.work_thread.start()



        elif str(self.sender().text()).startswith("Show PANDDAs Results"):
            print 'hallo', self.pandda_initial_html_file
            self.pandda_initial_html.load(QtCore.QUrl(self.pandda_initial_html_file))
            self.pandda_initial_html.show()
            self.pandda_analyse_html.load(QtCore.QUrl(self.pandda_analyse_html_file))
            self.pandda_analyse_html.show()
            self.pandda_inspect_html.load(QtCore.QUrl(self.pandda_inspect_html_file))
            self.pandda_inspect_html.show()

        elif str(self.sender().text()).startswith("Export PANDDA Models"):
            print '==> XCE: exporting pandda models with pandda.export'
            os.system('pandda.export pandda_dir="'+self.panddas_directory+'" out_dir="'+self.initial_model_directory+'"')




    def load_crystal_form_from_datasource(self):
        columns = ( 'CrystalFormName,'
                    'CrystalFormPointGroup,'
                    'CrystalFormVolume,'
                    'CrystalFormA,'
                    'CrystalFormB,'
                    'CrystalFormC,'
                    'CrystalFormAlpha,'
                    'CrystalFormBeta,'
                    'CrystalFormGamma,'
                    'CrystalFormSpaceGroup' )
        self.xtalform_dict={}
        all_xtalforms=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).execute_statement("SELECT "+columns+" FROM mainTable;")
        for item in all_xtalforms:
            name=item[0]
            pg=item[1]
            vol=item[2]
            a=item[3]
            b=item[4]
            c=item[5]
            alpha=item[6]
            beta=item[7]
            gamma=item[8]
            spg=item[9]
            add_crystalform=True
            for xf in self.xtalform_dict:
                if self.xtalform_dict[xf][0]==pg:      # same pointgroup as reference
                    try:
                        unitcell_difference=round((math.fabs(float(vol)-float(self.xtalform_dict[xf][1]))/float(vol))*100,1)
                    except (ValueError,TypeError):
                        unitcell_difference=100
                    if unitcell_difference < self.allowed_unitcell_difference_percent:      # suggest new crystal form
                        add_crystalform=False
                        break
            if add_crystalform:
                if str(name)=='None':
                    pass
                elif str(name)=='':
                    pass
                else:
                    self.xtalform_dict[name]=[pg,vol,[a,b,c,alpha,beta,gamma],spg]



    def no_data_source_selected(self):
        QtGui.QMessageBox.warning(self.window, "Data Source Problem",
                                      ('Please set or create a data source file\n')+
                                      ('Options:\n')+
                                      ('1. Use an existing file:\n')+
                                      ('- Settings -> Select Data Source File\n')+
#                                      ('- start XCE with command line argument (-d)\n')+
                                      ('2. Create a new file\n')+
                                      ('- Data Source -> Create New Data\nSource (SQLite)'),
                        QtGui.QMessageBox.Cancel, QtGui.QMessageBox.NoButton,
                        QtGui.QMessageBox.NoButton)



    def update_progress_bar(self,progress):
        self.progress_bar.setValue(progress)

    def update_status_bar(self,message):
        self.status_bar.showMessage(message)

    def thread_finished(self):
        self.explorer_active=0
        self.update_progress_bar(0)
        self.update_status_bar('idle')



    def create_widgets_for_autoprocessing_results(self,data_dict):
        self.data_collection_dict=data_dict

        # make sure not to overwrite previous selections!

        # in case we're just adding things to an existing table:

        if not self.main_data_collection_table_exists:
            self.main_data_collection_table=QtGui.QTableWidget()
            self.main_data_collection_table.setSortingEnabled(True)
            self.main_data_collection_table.setHorizontalHeaderLabels(['Sample','Date',''])
            self.main_data_collection_table.resizeRowsToContents()
            self.main_data_collection_table.setLineWidth(10)
            self.data_collection_vbox_for_table.addWidget(self.main_data_collection_table)
            self.main_data_collection_table_exists=True

        column_name = [ 'Program',
                        'Resolution\nOverall' ]

        # need to do this because db_dict keys are SQLite column names
        diffraction_data_column_name=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).translate_xce_column_list_to_sqlite(column_name)

#        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
#        table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
#        table.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.MinimumExpanding)
#        table.resizeColumnsToContents()

        row = self.main_data_collection_table.rowCount()

        for xtal in sorted(self.data_collection_dict):

            # first check if this sample exists in the table
            # use the outcome dict as an indicator since every sample should have one
            if xtal not in self.dataset_outcome_dict:
                self.main_data_collection_table.insertRow(row)

                # column 1: sample ID
                sample_ID=QtGui.QTableWidgetItem(xtal)
                sample_ID.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                self.main_data_collection_table.setItem(row, 0, sample_ID)

            # column 2: data collection date
            # this one should always be there; it may need updating in case another run appears
            # first find latest run
            tmp=[]
            for entry in self.data_collection_dict:
                if entry[0]=='image':
                    tmp.append(entry[3])
            data_collection_date_time=QtGui.QTableWidgetItem(max(tmp))      # not sure if this is really  as easy as max() !!!
            data_collection_date_time.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
            self.main_data_collection_table.setItem(row, 1, data_collection_date_time)

            # column 3:
            # ---------------------------------------------------------|
            # |                                                        |
            # | crystal images                                         |
            # |                                                        |
            # |--------------------------------------------------------|
            # |         |                                              |
            # | dataset |                                              |
            # | outcome | table for data processing results            |
            # | buttons |                                              |
            # |         |                                              |
            # |--------------------------------------------------------|

            # first check if it does already exist
            if xtal not in self.data_collection_column_three_dict:
                # geneerate all the widgets which can later be appended and add them to the dictionary
                cell_widget=QtGui.QWidget()
                vbox_cell=QtGui.QVBoxLayout(cell_widget)        # this is the main vbox for column 3
                hbox_for_button_and_table=QtGui.QHBoxLayout()
                layout = QtGui.QGridLayout()                    # for crystal images
                data_collection_table=QtGui.QTableWidget()      # table with data processing results for each pipeline
                self.data_collection_column_three_dict[xtal]=[cell_widget,vbox_cell,hbox_for_button_and_table,layout,data_collection_table]
                cell_widget.setLayout(vbox_cell)
                hbox_for_button_and_table.addWidget(data_collection_table)
                vbox_cell.addLayout(hbox_for_button_and_table)
            else:
                cell_widget =               self.data_collection_column_three_dict[xtal][0]
                vbox_cell =                 self.data_collection_column_three_dict[xtal][1]
                hbox_for_button_and_table = self.data_collection_column_three_dict[xtal][2]
                layout =                    self.data_collection_column_three_dict[xtal][3]
                data_collection_table =     self.data_collection_column_three_dict[xtal][4]
            vbox_cell.addLayout(layout)




            # this is necessary to render table properly
            data_collection_table.resizeRowsToContents()
            data_collection_table.resizeColumnsToContents()
            data_collection_table.horizontalHeader().setStretchLastSection(False)
            data_collection_table.verticalHeader().setStretchLastSection(True)
            data_collection_table.itemSelectionChanged.connect(self.update_selected_autoproc_data_collection_summary_table)
            data_collection_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            data_collection_table.setColumnCount(len(column_name))
            font = QtGui.QFont()
#            font.setFamily(_fromUtf8("Verdana"))
#            font =  self.horizontalHeader().font()
            font.setPointSize(8)
            data_collection_table.setFont(font)
            data_collection_table.setHorizontalHeaderLabels(column_name)
            data_collection_table.horizontalHeader().setFont(font)
            data_collection_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)


            #############################################################################
            # crystal images
            # first check there are new images that are not displayed yet; i.e. they are not in the self.data_collection_image_dict
            if xtal not in self.data_collection_image_dict:
                # OK this is the first time
                self.data_collection_image_dict[xtal]=[]

            # sort crystal images by timestamp
            # reminder: ['image',visit,run,timestamp,image_list,diffraction_image,run_number]
            # a) get only image entries from self.data_collection_dict
            tmp=[]
            for entry in self.data_collection_dict[xtal]:
                if entry[0]=='image':
                    tmp.append(entry)

            # b) sort by the previously assigned run number
            #    note: entry[6]==run_number
#            layout=self.data_collection_image_dict[xtal][0]
            for entry in sorted(tmp,key=lambda x: x[6]):
                run_number=entry[6]
                images_already_in_table=False
                for image in self.data_collection_image_dict[xtal]:
                    if run_number==image[0]:
                        images_already_in_table=True
                        break
                if not images_already_in_table:
                    for image_number,encoded_image in enumerate(entry[4]):
                # not if there is a run, but images are for whatever reason not present in self.data_collection_dict
                # then use image not available from $XChemExplorer_DIR/image/IMAGE_NOT_AVAILABLE.png
                # not sure how to do this at the moment; it will probably trigger an error that I can catch
                        pixmap = QtGui.QPixmap()
                        pixmap.loadFromData(base64.b64decode(entry[4][1]))
                        label = QtGui.QLabel()
                        label.resize(320,200)
                        label.setPixmap(pixmap.scaled(label.size(), QtCore.Qt.KeepAspectRatio))
                        layout.addWidget(label, run_number, image_number)
                    self.data_collection_image_dict[xtal].append([entry[6],entry[1],entry[2],entry[3],entry[5]])

            #############################################################################
            # data collection outcome box
            if xtal not in self.dataset_outcome_dict:
                # dataset outcome buttons
                dataset_outcome_groupbox=QtGui.QGroupBox()
                dataset_outcome_vbox=QtGui.QVBoxLayout()
                found_successful_data_collection=True
                for outcome in sorted(self.dataset_outcome):
                    button=QtGui.QPushButton(outcome)
                    button.setAutoExclusive(True)
                    button.setCheckable(True)
                    button.setStyleSheet("font-size:9px;background-color: "+self.dataset_outcome[outcome])
#                button.setFixedHeight(14)
                    button.clicked.connect(self.dataset_outcome_button_change_color)
                    self.dataset_outcome_dict[xtal].append(button)
                    dataset_outcome_vbox.addWidget(button)
                dataset_outcome_groupbox.setLayout(dataset_outcome_vbox)
                hbox_for_button_and_table.addWidget(dataset_outcome_groupbox)

            #############################################################################
            # table for data processing results
            # check if results from particular pipeline are already in table;
            # not really looking at the table here, but compare it to self.data_collection_table_dict
            row_position=data_collection_table.rowCount()
            if not xtal in self.data_collection_table_dict:
                self.data_collection_table_dict[xtal]=[]
            # reminder: ['logfile',visit,run,timestamp,autoproc,file_name,aimless_results,0,False]
            for entry in self.data_collection_dict:
                if entry[0]=='logfile':
                    entry_already_in_table=False
                    for logfile in self.data_collection_table_dict:
                        if entry[1]==logfile[1] and entry[2]==logfile[2] and entry[3]==logfile[3] and entry[4]==logfile[4]:
                            entry_already_in_table=True
                            break
                    if not entry_already_in_table:
                        data_collection_table.insertRow(row_position)
                        db_dict=entry[6]
                        for column,header in enumerate(diffraction_data_column_name):
                            cell_text=QtGui.QTableWidgetItem()
                            cell_text.setText(str( db_dict[ header[1] ]  ))
                            cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                            data_collection_table.setItem(row_position, column, cell_text)
                        best_file=entry[8]
                        if best_file:
                            data_collection_table.selectRow(row_position)
                        row_position+=1

                    self.data_collection_table_dict[xtal].append(['logfile',entry[1],entry[2],entry[3],entry[4]])   # 'logfile' is just added to have
                                                                                                                    # same index numbers between lists

            self.main_data_collection_table.setCellWidget(row, 2, cell_widget)
            self.main_data_collection_table.setColumnWidth(2, 1000)

#        self.populate_data_collection_summary_table()

        #-----------------------------------------------------------------------------------------------

    def update_xtalfrom_table(self,xtalform_dict):
        self.xtalform_dict=xtalform_dict
#        for key in self.xtalform_dict:
#            db_dict = {
#                'CrystalFormName':          key,
#                'CrystalFormSpaceGroup':    xtalform_dict[key][3],
#                'CrystalFormPointGroup':    xtalform_dict[key][0],
#                'CrystalFormA':             xtalform_dict[key][2][0],
#                'CrystalFormB':             xtalform_dict[key][2][1],
#                'CrystalFormC':             xtalform_dict[key][2][2],
#                'CrystalFormAlpha':         xtalform_dict[key][2][3],
#                'CrystalFormBeta':          xtalform_dict[key][2][4],
#                'CrystalFormGamma':         xtalform_dict[key][2][5],
#                'CrystalFormVolume':        xtalform_dict[key][1]       }
#            print db_dict

        self.crystal_form_table.setRowCount(0)
        self.crystal_form_table.setRowCount(len(self.xtalform_dict))
#        self.crystal_form_table.setColumnCount(len(self.crystal_form_column_name)-1)
        self.crystal_form_table.setColumnCount(len(self.crystal_form_column_name))
        all_columns_in_datasource=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).return_column_list()
        for y,key in enumerate(sorted(self.xtalform_dict)):
            db_dict = {
                'CrystalFormName':          key,
                'CrystalFormSpaceGroup':    xtalform_dict[key][3],
                'CrystalFormPointGroup':    xtalform_dict[key][0],
                'CrystalFormA':             xtalform_dict[key][2][0],
                'CrystalFormB':             xtalform_dict[key][2][1],
                'CrystalFormC':             xtalform_dict[key][2][2],
                'CrystalFormAlpha':         xtalform_dict[key][2][3],
                'CrystalFormBeta':          xtalform_dict[key][2][4],
                'CrystalFormGamma':         xtalform_dict[key][2][5],
                'CrystalFormVolume':        xtalform_dict[key][1]       }
            for x,column_name in enumerate(self.crystal_form_column_name):
                cell_text=QtGui.QTableWidgetItem()
                for column in all_columns_in_datasource:
                    if column[1]==column_name:
                        cell_text.setText(str(db_dict[column[0]]))
                        break
                cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                self.crystal_form_table.setItem(y, x, cell_text)
        self.crystal_form_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.crystal_form_table.resizeColumnsToContents()
        self.crystal_form_table.setHorizontalHeaderLabels(self.crystal_form_column_name)



    def create_initial_model_table(self,initial_model_list):

        self.initial_model_dimple_dict={}
        self.initial_model_table.setColumnCount(len(initial_model_list[0])-1)
        self.initial_model_table.setRowCount(0)
        self.initial_model_table.setRowCount(len(initial_model_list))

        for n,line in enumerate(initial_model_list):
            for column,item in enumerate(line[:-1]):
                if column==1:
                    run_dimple = QtGui.QCheckBox()
                    run_dimple.toggle()
                    self.initial_model_table.setCellWidget(n, column, run_dimple)
                    run_dimple.setChecked(line[1])
#                    self.initial_model_dimple_dict[line[0]]=run_dimple
                elif column==8:
                    # don't need to connect, because only the displayed text will be read out
                    reference_file_selection_combobox = QtGui.QComboBox()
#                    for reference_file in self.reference_file_list:
#                        reference_file_selection_combobox.addItem(reference_file[0])
                    self.populate_reference_combobox(reference_file_selection_combobox)
                    self.initial_model_table.setCellWidget(n, column, reference_file_selection_combobox)
                    index = reference_file_selection_combobox.findText(str(line[8]), QtCore.Qt.MatchFixedString)
                    reference_file_selection_combobox.setCurrentIndex(index)
                else:
                    cell_text=QtGui.QTableWidgetItem()
                    cell_text.setText(str(item))
                    cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                    self.initial_model_table.setItem(n, column, cell_text)
            self.initial_model_dimple_dict[line[0]]=[run_dimple,reference_file_selection_combobox]
#                r=item
#                g=item
#                b=item
#                initial_model_table.item(n,column).setBackground(QtGui.QColor(r,g,b))
        self.initial_model_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.initial_model_table.resizeColumnsToContents()
        self.initial_model_table.setHorizontalHeaderLabels(self.initial_model_column_name)

    def pandda_analyse_crystal_from_selection_combobox_changed(self,i):
        crystal_form = self.pandda_analyse_crystal_from_selection_combobox.currentText()
        self.populate_pandda_analyse_input_table(crystal_form)


    def get_reference_file_list(self,reference_root):
        # check available reference files
        reference_file_list=[]
        if os.path.isfile(os.path.join(self.reference_directory,reference_root+'.pdb')):
            pdb_reference=parse().PDBheader(os.path.join(self.reference_directory,reference_root+'.pdb'))
            spg_reference=pdb_reference['SpaceGroup']
            unitcell_reference=pdb_reference['UnitCell']
            lattice_reference=pdb_reference['Lattice']
            unitcell_volume_reference=pdb_reference['UnitCellVolume']
            pointgroup_reference=pdb_reference['PointGroup']
            reference_file_list.append([reference_root,
                                        spg_reference,
                                        unitcell_reference,
                                        lattice_reference,
                                        unitcell_volume_reference,
                                        pointgroup_reference])
        else:
            for files in glob.glob(self.reference_directory+'/*'):
                if files.endswith('.pdb'):
                    reference_root=files[files.rfind('/')+1:files.rfind('.')]
                    if os.path.isfile(os.path.join(self.reference_directory,reference_root+'.pdb')):
                        pdb_reference=parse().PDBheader(os.path.join(self.reference_directory,reference_root+'.pdb'))
                        spg_reference=pdb_reference['SpaceGroup']
                        unitcell_reference=pdb_reference['UnitCell']
                        lattice_reference=pdb_reference['Lattice']
                        unitcell_volume_reference=pdb_reference['UnitCellVolume']
                        pointgroup_reference=pdb_reference['PointGroup']
                        reference_file_list.append([reference_root,
                                                    spg_reference,
                                                    unitcell_reference,
                                                    lattice_reference,
                                                    unitcell_volume_reference,
                                                    pointgroup_reference])
        for i in reference_file_list:
            print i
        return reference_file_list


    def dataset_outcome_button_change_color(self):
#        print self.sender().text()
        outcome=''
        for key in self.dataset_outcome_dict:
            for button in self.dataset_outcome_dict[key]:
                if button==self.sender():
                    dataset=key
        for button in self.dataset_outcome_dict[dataset]:
            if button==self.sender():
                outcome=self.sender().text()
                if str(self.sender().text()).startswith('success'):
                    button.setStyleSheet("font-size:9px;background-color: rgb(0,255,0)")
                else:
                    button.setStyleSheet("font-size:9px;background-color: rgb(255,0,0)")
#                button.setStyleSheet("border-style: inset")
            else:
                button.setStyleSheet("font-size:9px;background-color: "+self.dataset_outcome[str(button.text())])
#        self.update_outcome_data_collection_summary_table(dataset,outcome)

        # change combobox in summary table
        dataset_outcome_combobox=self.dataset_outcome_combobox_dict[dataset]
        index = dataset_outcome_combobox.findText(str(outcome), QtCore.Qt.MatchFixedString)
        dataset_outcome_combobox.setCurrentIndex(index)


    def dataset_outcome_combobox_change_outcome(self,text):
        outcome=str(text)
        for key in self.dataset_outcome_combobox_dict:
            if self.dataset_outcome_combobox_dict[key]==self.sender():
                dataset=key

        for button in self.dataset_outcome_dict[dataset]:
            if str(button.text())==outcome:
                if outcome.startswith('success'):
                    button.setStyleSheet("font-size:9px;background-color: rgb(0,255,0)")
                else:
                    button.setStyleSheet("font-size:9px;background-color: rgb(255,0,0)")
            else:

                button.setStyleSheet("font-size:9px;background-color: "+self.dataset_outcome[str(button.text())])


    def set_run_dimple_flag(self,state):
        if state == QtCore.Qt.Checked:
            for key in self.initial_model_dimple_dict:
                self.initial_model_dimple_dict[key][0].setChecked(True)
        else:
            for key in self.initial_model_dimple_dict:
                self.initial_model_dimple_dict[key][0].setChecked(False)



    def populate_data_collection_summary_table(self):
        # 1. get length of table
        # 2. delete all entries
        self.data_collection_summary_table.setRowCount(0)
        self.albula_button_dict={}

        self.data_collection_summary_table.setRowCount(len(self.data_collection_statistics_dict))
        for row,key in enumerate(sorted(self.data_collection_statistics_dict)):
            # find which dataset_outcome_button is checked
            outcome=''
            for button in self.dataset_outcome_dict[key]:
                if button.isChecked():
                    outcome=button.text()

            # find which autoprocessing run was thought to be the best
            selected_processing_result=0
            for n,sample in enumerate(self.data_collection_statistics_dict[key]):
                # check which row was auto-selected
                for item in sample:
                    if isinstance(item, list):
                        if len(item)==2:
                            if item[0]=='best file':
                                if item[1]==True:
                                    selected_processing_result=n

#            print self.data_collection_statistics_dict[key][selected_processing_result]
            # find latest run
            # take all images from latest run and put in table
            tmp=[]
            for runs in self.data_collection_dict[key][0]:
                tmp.append(runs[1])
            latest_run=''
            visit=''
            diffraction_image=''
            for n,run in enumerate(self.data_collection_dict[key][0]):
                if run[1]==max(tmp):
                    latest_run=run[0]
                    visit=run[2]
                    if len(run)==4:
                        diffraction_image=os.path.join(str(run[3]),latest_run+'0001.cbf')
            images_to_show=[]
            if latest_run != '':
                for image in self.data_collection_dict[key][3]:
                    if latest_run in image[0] and image[0].endswith('t.png'):
                        images_to_show.append(image)
#                    for column in sorted(self.data_collection_dict[key][3]):
#                        if run[0] in column[0]:
#                            pixmap = QtGui.QPixmap()
#                            pixmap.loadFromData(base64.b64decode(column[1]))
#                            label = QtGui.QLabel()
#                            label.resize(320,200)
#                            label.setPixmap(pixmap.scaled(label.size(), QtCore.Qt.KeepAspectRatio))
#                            layout.addWidget(label, (run_number)*2+1, column_number)
#                            column_number+=1

            image_number=0
            for column,header in enumerate(self.data_collection_summary_column_name):
                cell_text=QtGui.QTableWidgetItem()
                if header=='Sample ID':
                    cell_text.setText(str(key))
                if header=='Dataset\nOutcome':

                    dataset_outcome_combobox = QtGui.QComboBox()
                    for outcomeItem in self.dataset_outcome:
                        dataset_outcome_combobox.addItem(outcomeItem)
                    self.data_collection_summary_table.setCellWidget(row, column, dataset_outcome_combobox)

                    index = dataset_outcome_combobox.findText(str(outcome), QtCore.Qt.MatchFixedString)
                    dataset_outcome_combobox.setCurrentIndex(index)

                    dataset_outcome_combobox.activated[str].connect(self.dataset_outcome_combobox_change_outcome)
                    self.dataset_outcome_combobox_dict[key]=dataset_outcome_combobox
                    #cell_text.setText(outcome)
                    continue

                if header.startswith('img'):
                    if len(images_to_show) > image_number:
                        pixmap = QtGui.QPixmap()
                        pixmap.loadFromData(base64.b64decode(images_to_show[image_number][1]))
                        image = QtGui.QLabel()
                        image.resize(80,50)
                        image.setPixmap(pixmap.scaled(image.size(), QtCore.Qt.KeepAspectRatio))
                        self.data_collection_summary_table.setCellWidget(row, column, image)
                        image_number+=1
                        continue
                    else:
                        cell_text.setText('')
                if header=='Puck':
                    puck='n/a'
#                    if len(self.data_collection_dict[key])==5:
#                        puck=self.data_collection_dict[key][4][0]
                    cell_text.setText(puck)
                if header=='Position':
                    position='n/a'
#                    if len(self.data_collection_dict[key])==5:
#                        position=self.data_collection_dict[key][4][1]
                    cell_text.setText(position)
                if header.startswith('Show'):
                    start_albula_button=QtGui.QPushButton('Show: '+latest_run+'0001.cbf')
                    start_albula_button.clicked.connect(self.button_clicked)
                    self.albula_button_dict[key]=[start_albula_button,diffraction_image]
                    self.data_collection_summary_table.setCellWidget(row,column,start_albula_button)
                for item in self.data_collection_statistics_dict[key][selected_processing_result]:
                    if isinstance(item, list):
                        if len(item)==3:
                            if item[0]==header:
                                cell_text.setText(str(item[1]))

                cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                self.data_collection_summary_table.setItem(row, column, cell_text)

        self.data_collection_summary_table.resizeRowsToContents()
        self.data_collection_summary_table.resizeColumnsToContents()

    def update_outcome_data_collection_summary_table(self,sample,outcome):
        rows_in_table=self.data_collection_summary_table.rowCount()
        for row in range(rows_in_table):
            if self.data_collection_summary_table.item(row,0).text()==sample:
                cell_text=QtGui.QTableWidgetItem()
                cell_text.setText(outcome)
                self.data_collection_summary_table.setItem(row, 3, cell_text)
#            self.data_collection_summary_table.resizeRowsToContents()
#            self.data_collection_summary_table.resizeColumnsToContents()

    def update_selected_autoproc_data_collection_summary_table(self):
        for key in self.data_collection_table_dict:
            if self.data_collection_table_dict[key]==self.sender():
                sample=key
                break

        indexes=self.sender().selectionModel().selectedRows()
        for index in sorted(indexes):
            selected_processing_result=index.row()


        rows_in_table=self.data_collection_summary_table.rowCount()
        for row in range(rows_in_table):
            if self.data_collection_summary_table.item(row,0).text()==sample:
#                print self.data_collection_summary_table.item(row,0).text()
                for column,header in enumerate(self.data_collection_summary_column_name):
                    cell_text=QtGui.QTableWidgetItem()
                    if header=='Sample ID':
                        continue
                    if header=='Dataset\nOutcome':
                        continue
                    for item in self.data_collection_statistics_dict[sample][selected_processing_result]:
                        if isinstance(item, list):
                            if len(item)==3:
                                if item[0]==header:
                                    cell_text.setText(str(item[1]))
                    cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                    self.data_collection_summary_table.setItem(row, column, cell_text)

    def populate_data_source_table(self,header,data):
        self.mounted_crystal_table.setColumnCount(0)
        self.mounted_crystal_table.setColumnCount(len(self.data_source_columns_to_display))
        self.mounted_crystal_table.setRowCount(0)

        columns_to_show=self.get_columns_to_show(self.data_source_columns_to_display,header)
        n_rows=self.get_rows_with_sample_id_not_null(header,data)
        self.mounted_crystal_table.setRowCount(n_rows)
        sample_id_column=self.get_columns_to_show(['Sample ID'],header)

        x=0
        for row in data:
            if str(row[sample_id_column[0]]).lower() == 'none' or str(row[sample_id_column[0]]).replace(' ','') == '':
                continue        # do not show rows where sampleID is null
            for y,item in enumerate(columns_to_show):
                cell_text=QtGui.QTableWidgetItem()
                if row[item]==None:
                    cell_text.setText('')
                else:
                    cell_text.setText(str(row[item]))
                if self.data_source_columns_to_display[y]=='Sample ID':     # assumption is that column 0 is always sampleID
                    cell_text.setFlags(QtCore.Qt.ItemIsEnabled)             # and this field cannot be changed
                cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                self.mounted_crystal_table.setItem(x, y, cell_text)
            x+=1
        self.mounted_crystal_table.setHorizontalHeaderLabels(self.data_source_columns_to_display)


    def populate_summary_table(self,header,data):
        self.summary_table.setColumnCount(len(self.summary_column_name))
        self.summary_table.setRowCount(0)
        self.summary_table.setRowCount(len(data))

        columns_to_show=self.get_columns_to_show(self.summary_column_name,header)
        for x,row in enumerate(data):
            for y,item in enumerate(columns_to_show):
                cell_text=QtGui.QTableWidgetItem()
#                if item=='Image':
#                    cell_text.setText('')
                if row[item]==None:
                    cell_text.setText('')
                else:
                    cell_text.setText(str(row[item]))
                if self.summary_column_name[y]=='Sample ID':     # assumption is that column 0 is always sampleID
                    cell_text.setFlags(QtCore.Qt.ItemIsEnabled)             # and this field cannot be changed
                cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                self.summary_table.setItem(x, y, cell_text)
        self.summary_table.setHorizontalHeaderLabels(self.summary_column_name)


    def populate_pandda_analyse_input_table(self,crystal_form):
        # load samples from datasource
        # show:
        # - sample ID
        # - crystal form name
        # - Dimple: resolution
        # - Dimple: Rcryst
        # - Dimple: Rfree
        #self.pandda_analyse_data_table
        self.pandda_analyse_data_table.setColumnCount(len(self.pandda_column_name))
        self.pandda_analyse_data_table.setRowCount(0)
        if os.path.isfile(os.path.join(self.database_directory,self.data_source_file)):
            content=XChemDB.data_source(os.path.join(self.database_directory,self.data_source_file)).load_samples_from_data_source()
            header=content[0]
            data=content[1]
            columns_to_show=self.get_columns_to_show(self.pandda_column_name,header)
            sample_id_column=self.get_columns_to_show(['Sample ID'],header)
            n_rows=0
            for x,row in enumerate(data):
                if str(row[sample_id_column[0]]).lower() == 'none' or str(row[sample_id_column[0]]).replace(' ','') == '':
                    continue        # do not show rows where sampleID is null
                for y,item in enumerate(columns_to_show):
                    if y==1:
                        if crystal_form=='use all datasets':
                            n_rows+=1
                        elif str(row[item]) == crystal_form:
                            n_rows+=1
            self.pandda_analyse_data_table.setRowCount(n_rows)

            x=0
            for row in data:
                if str(row[sample_id_column[0]]).lower() == 'none' or str(row[sample_id_column[0]]).replace(' ','') == '':
                    continue        # do not show rows where sampleID is null
                sample_id_exists=False
                crystal_from_of_interest=False
                # first run through every line and check if conditions above are fulfilled
                for y,item in enumerate(columns_to_show):
                    # y=0 is sample ID
                    if y==0:
                        if str(row[item]) != 'None' or str(row[item]).replace(' ','') != '':
                            sample_id_exists=True
                    if y==1:
                        if crystal_form=='use all datasets':
                            crystal_from_of_interest=True
                        elif str(row[item]) == crystal_form:
                            crystal_from_of_interest=True
                if sample_id_exists and crystal_from_of_interest:
                    for y,item in enumerate(columns_to_show):
                            cell_text=QtGui.QTableWidgetItem()
                            cell_text.setText(str(row[item]))
                            cell_text.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignCenter)
                            self.pandda_analyse_data_table.setItem(x, y, cell_text)
                    x+=1
        self.pandda_analyse_data_table.setHorizontalHeaderLabels(self.pandda_column_name)

    def get_columns_to_show(self,column_list,header_of_current_datasource):
        # maybe I coded some garbage before, but I need to find out which column name in the
        # data source corresponds to the actually displayed column name in the table
        # reason being that the unique column ID for DB may not be nice to look at
        columns_to_show=[]
        for column in column_list:
            # first find out what the column name in the header is:
            column_name=''
            for name in self.all_columns_in_data_source:
                if column==name[1]:
                    column_name=name[0]
            for n,all_column in enumerate(header_of_current_datasource):
                if column_name==all_column:
                    columns_to_show.append(n)
                    break
        return columns_to_show

    def get_rows_with_sample_id_not_null(self,header,data):
        sample_id_column=self.get_columns_to_show(['Sample ID'],header)
        n_rows=0
        for row in data:
#            if str(row[sample_id_column[0]]).lower() != 'none' or \
#            if not str(row[sample_id_column[0]]).replace(' ','') == '':
            if not str(row[sample_id_column[0]]).lower() != 'none' or not str(row[sample_id_column[0]]).replace(' ','') == '':
                n_rows+=1
        return n_rows





if __name__ == "__main__":
    app=XChemExplorer(sys.argv[1:])

