# ensure PL-rec-export is installed
# The following dir. structure is expected
# base_dir
#   |----> device_1
#   |         |----> Neon
#   |----> device_2
#   |         |----> Neon

# from multiprocessing import Pool
import subprocess
import questionary
import os, glob

def task(dir):
    print(f'Processing {dir} ...')

    #Run pl-rec-export
    try:
        res = subprocess.run(['pl-rec-export', '-f', '--blinks', dir], check=True) # add '-f' to force export, '--no-fixations', '--no-blinks'
        print(f'Finished processing {dir} !')
    except Exception as e:
        print(f"Error processing {dir}: {e}")

if __name__ == '__main__':
    
    base_dir = questionary.path("Select base dir with all recordings: ").ask()
    keyword_search = questionary.confirm("Filter recordings by keyword?").ask()
    keyword = ""
    if keyword_search:
        keyword = questionary.text("Enter keyword:").ask()

    for rec_dir in glob.glob(os.path.join(base_dir, "*/Neon/b5*/*")): 
        if keyword_search and keyword in rec_dir:
            task(rec_dir)
        elif not keyword_search:
            task(rec_dir)
    
    print('Done!')