This repo is made for Area Chairs of conferences that use OpenReview.  
Tired of having to manually copy ratings from OpenReview to your tracker spreadsheet?  
**Tire no more!**

### Step 0:
Create a virtualenv, install dependencies.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 1:
Enter your OpenReview credentials in the .env file.
```
USERNAME=<YOUR-USERNAME>
PASSWORD=<YOUR-PASSWORD>
```

### Step 2: 
Run the script to log into your account, gather submission info, and print it.
```bash
>> python run.py --conf iclr_2025 --headless

Opening https://openreview.net/group?id=ICLR.cc/2025/Conference/Area_Chairs
Logging in.
Waiting for page to finish loading...
Logged in.
Found 14 submissions.
1, 1234, Discovering the most boopable snoots, 8, 9, 10, 10
...
14, 4321, To boop or not to boop?, 5, 5, 4, 1
```
Skip `--headless` if you want to watch it do the web navigation.

If you want to try it on CVPR 2025, use `--conf cvpr_2025` and pass in the `--skip_reviews` flag
```bash
>> python run.py --conf cvpr_2025 --headless --skip_reviews

Opening https://openreview.net/group?id=thecvf.com/CVPR/2025/Conference/Area_Chairs
Logging in.
Waiting for page to finish loading...
Logged in.
Found 15 submissions.
1, 1234, To boop or not to boop?
...
15, 214, Ursidae are all you need
```
This is because the reviews for CVPR 2025 are probably not in yet, and the script will hang forever waiting for them to load.
