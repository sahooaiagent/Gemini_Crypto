# 🚀 Oracle Cloud Free Tier Deployment Guide

Complete guide to deploy your Crypto Scanner on Oracle Cloud (100% FREE forever)

---

## 📋 Prerequisites

- Oracle Cloud account (free)
- Your iPhone for testing
- SSH key (will be generated during setup)

---

## PART 1: Oracle Cloud Account Setup

### Step 1: Create Oracle Cloud Account

1. Visit: https://www.oracle.com/cloud/free/
2. Click **"Start for free"**
3. Fill in registration details:
   - Email address
   - Country/Region
   - Password (create strong password)
4. Verify your email
5. Add payment method (for verification only - **WON'T BE CHARGED**)
6. When prompted, choose **"Free Tier Only"**

### Step 2: Create VM Instance

1. **Login** to Oracle Cloud Console: https://cloud.oracle.com/
2. From the dashboard, click **"Create a VM Instance"**

   OR navigate: **Compute → Instances → Create Instance**

3. **Configure Instance:**

   | Setting | Value |
   |---------|-------|
   | **Name** | `crypto-scanner` |
   | **Compartment** | (keep default) |
   | **Placement** | (keep default) |

4. **Image and Shape:**
   - **Image:** Click "Change Image"
     - Select **"Ubuntu"**
     - Version: **22.04 Minimal** or **22.04**
     - Click "Select Image"

   - **Shape:** Click "Change Shape"
     - Click **"Ampere"** (ARM processor)
     - Select **VM.Standard.A1.Flex**
     - Set **OCPUs: 4**
     - Set **Memory: 24 GB**
     - Click "Select Shape"

   ✅ **This is FREE forever!**

5. **Networking:**
   - **Virtual cloud network:** (keep default)
   - **Subnet:** (keep default)
   - ✅ **IMPORTANT:** Check "Assign a public IPv4 address"

6. **SSH Keys:**
   - Select **"Generate a key pair for me"**
   - Click **"Save Private Key"** → Save as `oracle_key.key`
   - Click **"Save Public Key"** → Save as `oracle_key.pub`
   - **⚠️ IMPORTANT:** Save these files securely! You'll need them to access your server.

7. **Boot Volume:**
   - Keep defaults (50 GB is plenty)

8. Click **"Create"**

9. Wait 2-3 minutes for provisioning

10. **Copy your Public IP address** - you'll see it on the instance details page

---

## PART 2: Configure Firewall (Security Rules)

### Step 3: Open Port 8002 for Web Access

1. On your instance page, scroll to **"Primary VNIC"** section
2. Click on the **Subnet** link (e.g., "subnet-...")
3. Under **"Security Lists"**, click on **"Default Security List"**
4. Click **"Add Ingress Rules"**
5. Fill in:
   - **Source Type:** CIDR
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** TCP
   - **Source Port Range:** (leave empty)
   - **Destination Port Range:** `8002`
   - **Description:** `Crypto Scanner Web Dashboard`
6. Click **"Add Ingress Rules"**

---

## PART 3: Connect to Your VM

### Step 4: SSH Connection from Mac

Open **Terminal** on your Mac and run:

```bash
# Move SSH key to secure location
mkdir -p ~/.ssh
mv ~/Downloads/oracle_key.key ~/.ssh/oracle_key
chmod 400 ~/.ssh/oracle_key

# Connect to your VM (replace YOUR_PUBLIC_IP with actual IP)
ssh -i ~/.ssh/oracle_key ubuntu@YOUR_PUBLIC_IP
```

**Example:**
```bash
ssh -i ~/.ssh/oracle_key ubuntu@158.101.123.45
```

Type `yes` when asked about fingerprint.

---

## PART 4: Install Dependencies on VM

### Step 5: Update System & Install Python

Once connected via SSH, run these commands **one by one**:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python, pip, git, and build tools
sudo apt install python3 python3-pip python3-venv git build-essential wget -y
```

### Step 6: Install TA-Lib (Technical Analysis Library)

```bash
# Download and install TA-Lib
cd ~
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
cd ~
rm -rf ta-lib ta-lib-0.4.0-src.tar.gz
```

### Step 7: Configure VM Firewall (iptables)

```bash
# Allow incoming connections on port 8002
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8002 -j ACCEPT
sudo netfilter-persistent save
```

If you get an error about `netfilter-persistent`, install it:

```bash
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

---

## PART 5: Deploy Your Application

### Step 8: Clone Repository

```bash
# Clone your crypto scanner
git clone https://github.com/sahooaiagent/Gemini_Crypto.git
cd Gemini_Crypto
```

### Step 9: Setup Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt
```

**⏱️ This will take 5-10 minutes**

---

## PART 6: Test Your Application

### Step 10: Run the Scanner (Test)

```bash
# Make startup script executable
chmod +x start_scanner.sh

# Run the scanner
./start_scanner.sh
```

You should see:
```
============================
  🚀 Gemini Scanner Enterprise — Starting Server
============================

  Dashboard: http://0.0.0.0:8002
  API Docs:  http://0.0.0.0:8002/docs
```

### Step 11: Test from Your iPhone

1. Open **Safari** on your iPhone
2. Go to: `http://YOUR_PUBLIC_IP:8002`
3. You should see your Crypto Scanner dashboard!

**Example:** `http://158.101.123.45:8002`

If it works, **CONGRATULATIONS!** 🎉

Press `Ctrl+C` in the terminal to stop the scanner.

---

## PART 7: Setup Auto-Start Service

### Step 12: Create Systemd Service

This will make your scanner start automatically when the VM boots.

```bash
# Copy service file to systemd
sudo cp crypto-scanner.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable crypto-scanner

# Start the service now
sudo systemctl start crypto-scanner

# Check status
sudo systemctl status crypto-scanner
```

You should see `active (running)` in green.

### Step 13: Verify It's Working

```bash
# Check if service is running
sudo systemctl status crypto-scanner

# View live logs
sudo journalctl -u crypto-scanner -f
```

Press `Ctrl+C` to exit logs.

---

## 📱 Access from Your iPhone

1. Open **Safari** on your iPhone
2. Navigate to: `http://YOUR_PUBLIC_IP:8001`
3. Bookmark it for easy access!

---

## 🛠️ Useful Commands

### Check Service Status
```bash
sudo systemctl status crypto-scanner
```

### View Logs
```bash
# Live logs (Ctrl+C to exit)
sudo journalctl -u crypto-scanner -f

# Last 100 lines
sudo journalctl -u crypto-scanner -n 100
```

### Restart Service
```bash
sudo systemctl restart crypto-scanner
```

### Stop Service
```bash
sudo systemctl stop crypto-scanner
```

### Update Code from GitHub
```bash
cd ~/Gemini_Crypto
git pull origin main
sudo systemctl restart crypto-scanner
```

---

## 🔒 Security Best Practices

1. **Change SSH Port** (optional but recommended):
   ```bash
   sudo nano /etc/ssh/sshd_config
   # Change Port 22 to Port 2222
   sudo systemctl restart sshd
   ```

2. **Setup Firewall** (ufw):
   ```bash
   sudo apt install ufw -y
   sudo ufw allow 2222/tcp  # SSH (or 22 if you didn't change it)
   sudo ufw allow 8002/tcp  # Web dashboard
   sudo ufw enable
   ```

3. **Regular Updates**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

---

## 🐛 Troubleshooting

### Can't Access Dashboard?

1. **Check if service is running:**
   ```bash
   sudo systemctl status crypto-scanner
   ```

2. **Check firewall rules:**
   ```bash
   sudo iptables -L -n | grep 8002
   ```

3. **Check Oracle Cloud Security List** (Part 2, Step 3)

4. **View error logs:**
   ```bash
   sudo journalctl -u crypto-scanner -n 50
   ```

### Port Already in Use?
```bash
# Find what's using port 8002
sudo lsof -i :8002

# Kill the process if needed
sudo kill -9 <PID>
```

### Python Dependencies Failed?
```bash
cd ~/Gemini_Crypto
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

---

## 💰 Cost Breakdown

| Resource | Oracle Cloud Free Tier | Cost |
|----------|----------------------|------|
| VM.Standard.A1.Flex (4 OCPU, 24GB RAM) | ✅ Included | **$0/month** |
| 50 GB Boot Volume | ✅ Included | **$0/month** |
| Public IP Address | ✅ Included | **$0/month** |
| 10 TB Outbound Data Transfer/month | ✅ Included | **$0/month** |
| **TOTAL** | | **$0/month FOREVER** |

---

## 📞 Support

If you encounter issues:

1. Check the **Troubleshooting** section above
2. Review logs: `sudo journalctl -u crypto-scanner -n 100`
3. Verify Oracle Cloud Security List has port 8002 open
4. Ensure VM firewall allows port 8002

---

## 🎉 Success Checklist

- [x] Oracle Cloud account created
- [x] VM instance running
- [x] Port 8002 open in Security List
- [x] SSH connection working
- [x] Dependencies installed
- [x] Application cloned from GitHub
- [x] Service running and enabled
- [x] Accessible from iPhone Safari

**You're all set! Happy trading! 📈**
