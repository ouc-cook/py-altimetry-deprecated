# -*- coding: utf-8 -*-
"""
Created on Tue Oct 18 17:12:55 2011

@author: sskrypni

Last update: 03/2012
Use: 
 cdat-old
 python eval_run_profiles2.py --cfgfile='config_profiles.cfg'


"""

## utile pour ftp.retrbinary
#def handleDownload(block):
#    file.write(block)
#    #print ".",

def isNaN(num):
    return num != num

def get_ftp_f1(ctdeb, ctfin,andeb, SCRIPT_DIR, dirf1, usr, pwd, fic_prefix, time_res):
    import os,cdtime, subprocess, ConfigParser
    print 'ftp cdoco en cours'
    # connection au F1/F2 au CDOCO
    
    base_filename = os.path.join(dirf1,str(andeb)) 
    ctest = ctdeb
    current_year = ctdeb.year
    while ctest <= ctfin: 
         
        # si on change d'annee alors on change de repertoire
        if ctest.year != current_year:
            current_year = ctest.year
            base_filename = os.path.join(dirf1,str(ctest.year)) 
         
        #construction du nom de fichier
        fic = fic_prefix+'%4d%02d%02dT%02d00Z.nc' %(ctest.year,ctest.month,ctest.day,ctest.hour)
        filename = ''
        filename=os.path.join(base_filename,fic)
        #print filename
         
        # recuperation fichier si non present dans work/MODEL/MARS
        if os.path.isfile(fic)==False:
            full_filename = 'ftp://%(usr)s:%(pwd)s@%(filename)s' %vars()
            print full_filename
            subprocess.call(["wget", full_filename])
        else:
            print "No ftp copy needed : %(fic)s already exists."%vars()
         
        # On incremente le temps "test" de 1 ou  3 heures (time_res)
        ctest=ctest.add(time_res,cdtime.Hours)


# ------------------------------------------------------------------
# Import des librairies necessaires

## -- These two line allows running without display
## Warning: does not allow screen figure display
#import matplotlib
#matplotlib.use('Agg')
## --
from genutil import statistics
from vacumm.misc.grid import get_grid,  set_grid
		
from vacumm.data.misc.profile import ProfilesDataset, ProfilesMerger 
from vacumm.data.model.mars import MARS3D
from vacumm.data.misc.coloc import Colocator
from vacumm.misc.atime import strptime, strtime, numtime, strftime, comptime, Intervals
#import vacumm.data.misc.profile as P
#from vacumm.data.in_situ.recopesca import Recopesca, Profile
import matplotlib.pyplot as P
import matplotlib.dates as date
from scipy import interpolate
from vacumm.misc.plot import map2 as map
from vacumm.misc.plot import bar2 as bar
from vacumm.misc.plot import savefigs
from vacumm.misc.color import ocean
import vacumm.misc.atime as atime
from vacumm.data.misc.handle_directories import make_directories
from vacumm.misc.io import ncread_best_estimate, NcIterBestEstimate, list_forecast_files
from vacumm.misc.grid.regridding import grid2xy, interp1d
from vacumm.misc.axes import create_time, create_lat, create_lon
from vacumm.data.misc.sigma import NcSigma
from vacumm.misc.config import ConfigManager, print_short_help
from optparse import OptionParser, sys, os
from vacumm.validator.valid.ValidXYT import ValidXYT

import optparse
import numpy as np
import glob, os, sys, shutil, ConfigParser, gc
import pylab
import cdtime
import pytz
import cdms2
import MV2

# Pour les tests ... pour explorer les objets
import inspect

from cdms2.selectors import time

from cprofile import Profile, Prof_insitu

cdms2.setNetcdfShuffleFlag(0); cdms2.setNetcdfDeflateFlag(0); cdms2.setNetcdfDeflateLevelFlag(0)
def write_nc_cf(filename, varin1=None,varin2=None,):
    config = ConfigParser.RawConfigParser()
    config.read(os.path.join(SCRIPT_DIR,'config_profiles.ini'))
    rep_ecriture= config.get('Output','rep_ecriture')
    filename= os.path.join(rep_ecriture,filename)
    f = cdms2.open(filename, 'w')
    f.write(varin1) # ecriture d'une variable    
    f.write(varin2) #ecriture
	
    creation_date = time.strftime('%Y-%m-%dT%H:%M:%SZ')
    f.creation_date = creation_date
    f.title = config.get('Output','title')
    #print f
    f.close() # fermeture

if __name__ == '__main__':
    # ========================================================================
    # Options d'utilisation:

    parser = OptionParser(usage="Usage: %prog [options]",
    description="Script to explore vertical profiles and to validate model run using these profiles.", add_help_option=False )
    parser.add_option('-h','--help', action='store_true', 
                      dest="help", help='show a reduced help')
    parser.add_option('--long-help', action='store_true', 
                      dest="long_help", help='show an extended help')

    # Define config manager     
    cfgm = ConfigManager('config_profiles.ini')
    #cfg = cfgm.load()

    # Get config from commandline options
    cfgpatch = cfgm.opt_parse(parser)

    # Pour afficher le fon fichier par defaut
    parser.defaults['cfgfile']=cfgm._configspecfile

    # Help
    opts = parser.values
    #args = parser.largs
    if opts.long_help:
        parser.print_help()
        sys.exit()
    elif opts.help:
        print_short_help(parser)
        sys.exit()

    #if len(args) < 1 or not os.path.exists(args[0]):
    #    parser.error('You must provide a valid netcdf file name as first argument')
    #ncfile = args[0]
    
    # Complete config
    # - load personal file and default values
    cfg = cfgm.load(opts.cfgfile)
    # - patch with commandeline options
    cfgm.patch(cfg, cfgpatch)
    
    # Check config
    #print 'Current configuration:', cfg


    print 65 * '-'
    print ' Validation de la Temperature et Salinite a partir des profils verticaux '
    print 65 * '-'
    
    # -- Actions et Environnement 
    # ----------------------------------------------------------------
    print ' Definition des parametres d environnement '
    print 65 * '-'
    
    # ---------------------------------------------------------
    # Cette partie doit etre codee dans le setup.py !!!!
    SCRIPT_DIR = os.getcwd()
    #config = ConfigParser.RawConfigParser()
    #config.read(os.path.join(SCRIPT_DIR, configfile))    
    #model_name = config.get('Model Description', 'name')
    model_name = cfg['Model Description']['name']    

    # Workdir    
    WK_DIR = cfg['Env']['workdir']
    obs_product = cfg['Observations']['product']
    obs_product = obs_product.replace(' ', '_')
    
    os.chdir(SCRIPT_DIR)
    if os.path.isdir(SCRIPT_DIR + '/Figures') == False:
            os.mkdir('Figures')
    os.chdir(SCRIPT_DIR + '/Figures')
    if os.path.isdir(SCRIPT_DIR + '/Figures/' + obs_product) == False:
            os.mkdir(obs_product)
    FIG_DIR = os.path.join(SCRIPT_DIR, 'Figures', obs_product) 
    
    os.chdir(SCRIPT_DIR)
    # Fin setup.py
    # -----------------------------------------------------------------
    
    # -- Obs: Rappatriement et lecture des observations corespondantes a la periode consideree
    # ----------------------------------------------------------------
    print ' -- Lecture des profils RECOPESCA --    '
    print 65 * '-'
    if cfg['Observations']['product'] == 'RECOPESCA':
        obs = Prof_insitu(cfg) # ... a passer en librairie ...
       
                
    if cfg['Observations']['downloadlatest'] == 'True':
        obs.rappatrie(cfg)
    
    obs.read(cfg)
    
    #print obs.map_profiles

    if cfg['Env']['use_model']== 'True':
        # ----------------------------------------------------------------
        # ----------------------------------------------------------------
        print ' -- Lecture des sorties de modeles --    '
        print 65*'-'
        
        # changement de repertoire et creation eventuelle de nouveaux repertoires
        # les fichiers modeles sont rapatries dans vacumm/work/MODEL/MARS
        dir_one ='MODEL'
        
        #dir_two = 'MARS'
        dir_two=cfg['Model Description']['name'].upper() 
        
        # Cree les repertoires et se positionne dans le repertoire de rapatriment des fichiers
        make_directories(SCRIPT_DIR, WK_DIR,  dir_one, dir_two)
        
    andeb = cfg['Time Period']['andeb']    
    anfin = cfg['Time Period']['anfin']
    mdeb = cfg['Time Period']['mdeb']
    mfin = cfg['Time Period']['mfin']
    jdeb = cfg['Time Period']['jdeb']
    jfin = cfg['Time Period']['jfin']
    hdeb = cfg['Time Period']['hdeb']
    hfin = cfg['Time Period']['hfin']
    # fin lecture de config.cfg
    
    ctdeb=cdtime.comptime(andeb,mdeb,jdeb,hdeb,0,0)   
    ctfin=cdtime.comptime(anfin,mfin,jfin,hfin,0,0)
        
        
    print ctdeb
    print ctfin        
        
        
    if cfg['Env']['use_model']=='True':
        # rapatriement donnees F1 
        # voir note readme_rapatriement_f1.py
        dir_model = './' # Default / 
        if cfg['Model Description']['download'] == 'ftp':
            dirf1 = cfg['MARS F1']['url_f1']
            usr = cfg['MARS F1']['user']
            pwd = cfg['MARS F1']['pwd']
            fic_prefix = cfg['MARS F1']['fic_prefix']       #'PREVIMER_F1-MARS3D-MANGA4000_'
            time_res = cfg['MARS F1']['time_res']   # pas de temps des sorties en heure
            # recuperation f1 via FTP
            get_ftp_f1(ctdeb, ctfin,andeb, SCRIPT_DIR, dirf1, usr, pwd, fic_prefix, time_res)
              
        if cfg['Model Description']['download'] == 'local_dir':
            # Pour cette option, les sorties modeles sont directement lues dans "output_dir"
            dir_model = cfg['Model Description']['output_dir']
        else:
            dir_model = os.getcwd()
        print 'Read model output in ', dir_model 
        print '---'
        
        if cfg['Model Description']['name'] == 'mars_manga':
            fic_prefix = cfg['MARS F1']['fic_prefix']       #'PREVIMER_F1-MARS3D-MANGA4000_'
            time_res = cfg['MARS F1']['time_res']   # pas de temps des sorties en heure
        
        # Repositionnement dans le repertoire 'bin' de lancement du script
        os.chdir(SCRIPT_DIR)
        
        # --------------------------------------------------------------------------
        # --------------------------------------------------------------------------
    
    # model: contient les champs 3D du modele sur la periode consideree ...
    # obs: dictionnaire des profils


        
    # Création map temporaire         
    map_profiles_model = {}
    map_profiles_obs = {}
    
    # Boucle sur les differents profils
    for it, val in obs.map_profiles.items():
        #print it
        #print val
        scircle = .5 # Taille en degres de la zone de recherche de points modele: lon+/-scircle et lat+/-scircle        
        
        proftime = cdtime.s2c(it)
        
        # Selection des profils pour la periode dans config_profiles.cfg 
        if proftime >= ctdeb and proftime <= ctfin:
            #print proftime
            c1 = proftime
            c1=c1.sub(1,cdtime.Hours)        
            c2 = proftime
            c2 = c2.add(2,cdtime.Hours) # Car en prenant c1,c2 ... 3 fichiers horaires sont selectionnes mais seuls les 2 premiers sont lus.
            
            if    cfg['Env']['use_model']=='True':         
                
                lo = float(val.lon)
                la = float(val.lat)
                filepattern =  os.path.join(dir_model,fic_prefix+"%Y%m%dT%H00Z.nc")
                time = (c1,c2)
                #ncfiles = list_forecast_files(filepattern, time)
                #print ncfiles
                if cfg['Model Description']['name'] == 'mars_manga':            
                    model = ncread_best_estimate('TEMP',filepattern, time,select=dict(lon=(lo-scircle,lo+scircle), lat=(la-scircle,la+scircle)))
                    model2 = ncread_best_estimate('SAL',filepattern, time,select=dict(lon=(lo-scircle,lo+scircle), lat=(la-scircle,la+scircle)))

                ncfiles = list_forecast_files(filepattern, time)              
                depth=()
                for f,t in NcIterBestEstimate(ncfiles, time):
		    
		    
                    sigma = NcSigma.factory(f)
                    d = sigma(copyaxes=True)
		    depth+=d(lon=(lo-scircle,lo+scircle), lat=(la-scircle,la+scircle)),
		    print type(d)
		    del d
		    gc.collect()
		depth=MV2.concatenate(depth)
		
		
		#print dir(d)
                # Interpolation temporelle du modele sur le temps du profil observé
                modeltime = model.getTime()
                new_time = create_time(proftime, modeltime.units)  
                model = interp1d(model, new_time, method='linear') 
                depth = interp1d(depth, new_time, method='linear')
                model2 = interp1d(model2, new_time, method='linear') 
		
		for i in (0, model.shape[1]):
		# centered and biased std (cf. http://www2-pcmdi.llnl.gov/cdat/manuals/cdutil/cdat_utilities-2.html)
		    std_temp = () #Initialise un tuple
		    std_sal = () #Initialise un tuple
		 
		    temp_model=np.reshape(model[0,:,:,:],(model.shape[1],model.shape[2]*model.shape[3]))
		    temp_model2=np.reshape(model2[0,:,:,:],(model2.shape[1],model2.shape[2]*model2.shape[3]))
		  
		    std_temp += statistics.std(temp_model, axis = 1),
		    std_sal  += statistics.std(temp_model2, axis = 1),
		
		  		
		std_temp=MV2.concatenate(std_temp)
		std_sal=MV2.concatenate(std_sal)
		
		
		ggT = model.getLevel()        
		std_temp.setAxis(0, ggT)   
		
		ggS = model2.getLevel()        
		std_sal.setAxis(0, ggS)
		
		
		#print ggS.getAxisList()

                #Interpolation spatiale du modele sur la position du profil observé
                model = grid2xy(model[0,:,:,:], lo, la, method='bilinear') # Ne fonctionne pas avec 'nat' pour Natgrid
                model2 = grid2xy(model2[0,:,:,:], lo, la, method='bilinear') 
                depth = grid2xy(depth[0,:,:,:], lo, la, method='bilinear')
                #std_temp = grid2xy(std_temp[:], lo, la, method='bilinear')
                #std_sal = grid2xy(std_sal[:], lo, la, method='bilinear')
                #print std_sal.shape
                #print std_temp.shape
                          # Dictionnaire profil modele
            time2 = date.num2date(numtime(val.time))
            key = strtime(time2)
	    
            
            if    cfg['Env']['use_model']=='True':
                profile = Profile(val.time, val.platform_name, val.lon, val.lat, cfg)
                profile.add_time_step(depth.getValue(), model.getValue(), model2.getValue())
                map_profiles_model[key] = profile
            
            profile2 = Profile(val.time, val.platform_name, val.lon, val.lat, cfg)
            profile2.add_time_step(val.depth, val.temp, val.sal,None,None)
            map_profiles_obs[key] = profile2
   
    
    for key in map_profiles_obs:
        if    cfg['Env']['use_model']=='True':
            profile = map_profiles_model[key]
            profile.convert_tables()
        profile2 = map_profiles_obs[key]
        profile2.convert_tables()
  
    print 65*'-'
    print str(len(map_profiles_obs))+' profils .'
    print 65*'-'

    # Boucle sur les differents profils
    lon_pro=np.zeros(len(map_profiles_obs))
    lat_pro=np.zeros(len(map_profiles_obs))
    time_pro=np.zeros(len(map_profiles_obs))
    cpt=0
    for it, val in map_profiles_obs.items():     
        ittag = '_'.join(''.join(''.join('_'.join(it.split(' ')).split('-')).split(':')).split('.'))
        
        if cfg['Action']['single_profiles']=='True':
        
            print 'Min:'+str(map_profiles_obs[it].temp.min())        
            print 'Max:'+str(map_profiles_obs[it].temp.max())
            
            P.figure(1)
            if    cfg['Env']['use_model']=='True':
                P.plot(map_profiles_model[it].temp[0,:,0],-map_profiles_model[it].depth[0,:,0],'r')
            P.plot(map_profiles_obs[it].temp[0,:],-map_profiles_obs[it].depth[0,:])            
            savefigs(os.path.join(FIG_DIR,'Observed_profile_'+ittag))
            P.close(1)

        
        if cfg['Action']['map_profiles']=='True' or cfg['Action']['hist_profiles']=='True':
            lon_pro[cpt]=map_profiles_obs[it].lon
            lat_pro[cpt]=map_profiles_obs[it].lat
            time_pro[cpt]=date.date2num(map_profiles_obs[it].time)
            cpt=cpt+1

    if cfg['Action']['map_profiles']=='True':
        P.figure()
        #LONGITUDE = create_lon(lon_pro, id='longitude', attributes=dict(long_name='Longitude of each location',standard_name='longitude',units='degrees_east',valid_min='-180.',valid_max='180.',axis='X'))
        #LATITUDE = create_lat(lat_pro, id='latitude', attributes=dict(long_name='Latitude of each location',standard_name='latitude',units='degrees_north',valid_min='-90.',valid_max='90.',axis='Y'))
        #profile_date = 
        ray = 1 
        titre = 'Observed profiles'
        mp = map(show=False, lon=(lon_pro.min()-ray,lon_pro.max()+ray), lat=(lat_pro.min()-ray,lat_pro.max()+ray), title=titre)
        sc = mp.map.scatter(lon_pro,lat_pro,c=time_pro)
        cb = P.colorbar(sc)
        
        # --- Creation des dates pour les label de la colorbar
        #ticklabels = cb.ax.get_yticklabels()
        ticklim = cb.get_clim()
        ticklabels=np.linspace(ticklim[0],ticklim[1],num=8)
        time_str=[]
        for il in ticklabels:
            time_str.append(date.num2date(il).strftime('%Y/%m/%d'))
        
        cb.set_ticks(ticklabels)
        cb.set_ticklabels(time_str)
        
        
        savefigs(os.path.join(FIG_DIR,'Map_profiles'+strftime('%Y%m%d',ctdeb)+'_'+strftime('%Y%m%d',ctfin)))
        P.close()
        #P.show()
        
    if cfg['Action']['hist_profiles']=='True':
        
        # Extrait de                 
        tstep = cfg['Histogram']['tstep']
        tstep_unit = cfg['Histogram']['tstep_unit']
        dtime = date.num2date(time_pro)        
        npro = len(dtime)
        hist, hist_time = [], []
        
        
        utc=pytz.UTC

        
        for itv in Intervals((atime.round_date(min(dtime), tstep_unit), atime.round_date(atime.add(max(dtime), tstep, tstep_unit), tstep_unit)),(tstep,tstep_unit)):
            hist_time.append(atime.datetime(itv[0]))            
            t1 = utc.localize(atime.datetime(itv[0]))
            t2 = utc.localize(atime.datetime(itv[1]))
            n = len(filter(lambda d: t1 <= d < t2, dtime))
            hist.append(n)
            #print 'Interval %(#)s: %(##)s'%{'#':itv[:2],'##':n}
        hist_time = create_time(hist_time)
        hist = cdms2.createVariable(hist, axes=(hist_time,), id='hist', attributes=dict())
        
        P.figure()
        cs = bar(hist,xlabel='time',ylabel='Number of profiles',title='Profiles temporal distribution')
        print '### voir pour reformattage des datmap_profiles_model[it].depth.squeeze()es (axe x de l''histogramme). ###'
            
    if cfg['Action']['mean_profile']=='True':
        print "---- Function not implemented ----"
        sys.exit()
        
        
    # ---- Creation d'un objet cdms avec pour axe=(temps,depth)

    # -- Maximum depth for selcted profiles
    depthmax=0
    for it, val in map_profiles_obs.items():
        if map_profiles_obs[it].depth.max() > depthmax:
            depthmax = map_profiles_obs[it].depth.max()
    #print 'Max depth = '+str(depthmax)+' m'
    # --
    # -- Depth Axes
    depthax = np.arange(0,depthmax)
    
    TEMP_obs = np.zeros((len(map_profiles_obs),len(depthax)))
    SAL_obs = np.zeros((len(map_profiles_obs),len(depthax)))
    TEMP_model = np.zeros((len(map_profiles_model),len(depthax)))
    SAL_model = np.zeros((len(map_profiles_model),len(depthax)))
    cpt=0
    b=[]
    
    for it, val in map_profiles_obs.items():        

	f=interpolate.interp1d(map_profiles_obs[it].depth.squeeze(),map_profiles_obs[it].temp.squeeze(),bounds_error=False)
        TEMP_obs[cpt,:]=f(depthax)
        f2=interpolate.interp1d(map_profiles_obs[it].depth.squeeze(),map_profiles_obs[it].sal.squeeze(),bounds_error=False)
        SAL_obs[cpt,:]=f2(depthax)
	b.append(numtime(map_profiles_obs[it].time))
       
        cpt+=1
    cpt=0
    
    for it, val in map_profiles_model.items():        

	
        f=interpolate.interp1d(map_profiles_model[it].depth.squeeze(),map_profiles_model[it].temp.squeeze(),bounds_error=False)
        TEMP_model[cpt,:]=f(depthax)
        f2=interpolate.interp1d(map_profiles_model[it].depth.squeeze(),map_profiles_model[it].sal.squeeze(),bounds_error=False)
	SAL_model[cpt,:]=f2(depthax)
	cpt+=1
    
    cpt=0
    #print std_temp
    #for it, val in map_profiles_model.items():        

	
        #f=interpolate.interp1d(std_temp[it].depth.squeeze(),std_temp[it].temp.squeeze(),bounds_error=False)
        #std_temp[cpt]=f(depthax)
        #f2=interpolate.interp1d(std_sal[it].depth.squeeze(),std_sal[it].sal.squeeze(),bounds_error=False)
	#std_sal[cpt]=f2(depthax)
	#cpt+=1
    #print std_temp
    # --------------------------------------------------------------------
    # Temps
    # - creation et tri des dates
    
    I=np.argsort(b)
    b=np.array(b)
    b=b[I]
    axtime = cdms2.createAxis(b[:],id='time')
    axtime.long_name = 'Time'
    axtime.units = 'days since 2006-08-01'
    axtime.designateTime() # time.axis = 'T'

    for it, val in map_profiles_obs.items():
	print 'Min:'+str(map_profiles_obs[it].temp.min())        
	print 'Max:'+str(map_profiles_obs[it].temp.max())
    #print 'Voir comment convertir temps 2010-3-20 9:45:8.0 en temps relatif puis retrier les profils par date'
    #print 'Ensuite créer 2 autres variables cdms2 uniquement d''axe temps contenant lon et lat'
    #print 'pour la selection en lon,lat ... retrouver les indices des regions dans lon et lat puis faire un select dans la variable cdms de temperature (et lon, lat)'

    #print 69*'-'
    #print 'axtime'
    #print axtime
    axdepth = cdms2.createAxis(depthax,id='depth')
    axdepth.long_name = 'Depth'
    axdepth.units = 'm'
    axdepth.designateLevel() # depth.axis = 'Z'
    #print 'axdepth'
    #print axdepth
    #  -> [2006-8-1 0:0:0.0, 2006-8-2 0:0:0.0, 2006-8-3 0:0:0.0] 2
    #rtime = ctime.asRelativeTime()
    
    
    #print rtime,rtime[1].value    
    #print 69*'*'


    TEMP_obs=TEMP_obs[I, :]
    SAL_obs=SAL_obs[I, :]
    
   
    #  -> [0.00 days since 2006-08-01, 1.00 days since 2006-08-01,
    #      2.00 days since 2006-08-01] 1.0
    # -------------------------------------------------------------------------
	
    
    TEMP_obs=MV2.masked_array(TEMP_obs,mask=isNaN(TEMP_obs))
    SAL_obs=MV2.masked_array(SAL_obs,mask=isNaN(SAL_obs))

    TEMP_obs = cdms2.createVariable(TEMP_obs,typecode='f',id='temp_obs',
                                    fill_value=1.e20,axes=[axtime,axdepth],
                                    attributes=dict(long_name='OBserved Temperature',units='degC'))
    SAL_obs = cdms2.createVariable(SAL_obs,typecode='f',id='sal_obs',
                                   fill_value=1.e20,axes=[axtime,axdepth],
                                   attributes=dict(long_name='Observed Salinity',units='Psu'))
    TEMP_model = cdms2.createVariable(TEMP_model,typecode='f',id='temp_model',
                                    fill_value=1.e20,axes=[axtime,axdepth],
                                    attributes=dict(long_name='Modeled Temperature',units='degC'))
    SAL_model = cdms2.createVariable(SAL_model,typecode='f',id='sal_model',
                                   fill_value=1.e20,axes=[axtime,axdepth],
                                   attributes=dict(long_name='Modeled Salinity',units='Psu'))   
    
    # Maintenant, on cree une variable avec ces axes
    #- methode direct
    #temp1 = cdms2.createVariable(N.ones((3,3,3,3)),typecode='f',id='temp',
    #fill_value=1.e20,axes=[time,depth,lat,lon],copyaxes=0,
    
	
    # -- Interpolation sur la verticale des profils
     
        
    #if cfg['Action']['timeserie_profile']=='True':
        ## -- Read the file with subregions coordinates
        #file_data = open(os.path.join(SCRIPT_DIR,'fishing_areas.dat')).read()                                   
        ##extraction des profil du fichier (ligne a ligne)
    
        #for line in file_data.splitlines():
            #line = line.strip().split(',')                    
            #region_name = line[0]
            #lamin = float(line[1])
            #lamax = float(line[2])
            #lomin = float(line[3])
            #lomax = float(line[4])            
            
            #print region_name
            #print lamin
            #print lamax
            #print lomin
            #print lomax
    print 65*'-'
    
    


    print ' -- Validation Profils (Global) --    ' 
    print 65*'-'
    
    tag = 'all'
    tagbegin= strftime('%Y%m%d',ctdeb)
    tagend= strftime('%Y%m%d',ctfin)
    

    print 65*'-'
    print  'La validation concerne les modeles et observations compris entre '+tagbegin+' jusqu au ' +tagend
    print 65*'-'
    
    tagforfilename = '_'.join(tag.split(' ')).lower()
    tagforfiledate1 = '_'.join(tagbegin.split(' ')).lower()    
    tagforfiledate2 = '_'.join(tagend.split(' ')).lower()
    #data_obs=save(obs,'/work/sskrypni/data_test/')
    #data_obs.plot_hist()
    #obs= TEMP_obs
    print 'TEMP_obs'
    print TEMP_obs.view()
    #print TEMP_obs.shape()
    print 'SAL_obs'
    print SAL_obs.view()
    #print SAL_obs.shape()
    print 'TEMP_model'
    print TEMP_model.view()
    #print TEMP_model.shape()
    print 'SAL_model'
    print SAL_model.view()
    #print SAL_model.shape()
    print 65*'*'
    
    gc.collect()
    sys.exit()              

           
        
