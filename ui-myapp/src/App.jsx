// src/App.js
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [peers, setPeers] = useState({});
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [sendingStatus, setSendingStatus] = useState('');
  const [useMultiple, setUseMultiple] = useState(false);
  const [selectedPeers, setSelectedPeers] = useState([]);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [availableFiles, setAvailableFiles] = useState([]);

  // Fetch peers from bootstrap server
  useEffect(() => {
  const fetchPeers = async () => {
    try {
      // Change this to call the controller instead of bootstrap directly
      const response = await axios.get('http://localhost:5000/peers');
      setPeers(response.data);
      
      // Extract all unique files
      const files = new Set();
      Object.values(response.data).forEach(peer => {
        peer.files.forEach(file => files.add(file));
      });
      setAvailableFiles([...files]);
    } catch (error) {
      console.error('Error fetching peers:', error);
    }
  };
  
  fetchPeers();
  const interval = setInterval(fetchPeers, 5000);
  return () => clearInterval(interval);
}, []);

  // Handle file drag events
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  // Send file to selected peers
  const sendFile = async () => {
    if (!selectedFile) {
      setSendingStatus('Please select a file first');
      return;
    }
    
    setSendingStatus('Sending file...');
    
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      
      await axios.post('http://localhost:5000/send', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      
      setSendingStatus('File sent successfully!');
      setSelectedFile(null);
    } catch (error) {
      console.error('Error sending file:', error);
      setSendingStatus('Failed to send file');
    }
  };

  // Receive file from peers
  const receiveFile = async () => {
  if (useMultiple && selectedPeers.length === 0) {
    setDownloadStatus('Please select at least one peer');
    return;
  }

  setDownloadStatus('Downloading file...');

  try {
    const response = await axios.post('http://localhost:5000/receive', {
      useMultiple,
      peers: selectedPeers
    });

    setDownloadStatus(response.data.message || 'Download initiated...');

    // Wait for reconstruction to complete (adjust delay if needed)
    setTimeout(async () => {
      const filename = 'myfile.txt'; // Replace this with your actual reconstructed filename
      try {
        const res = await axios.get(`http://localhost:5000/download/${filename}`, {
          responseType: 'blob'
        });

        const url = window.URL.createObjectURL(new Blob([res.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();
        link.remove();
        setDownloadStatus('File downloaded successfully!');
      } catch (err) {
        setDownloadStatus('Failed to download reconstructed file');
        console.error('Download error:', err);
      }
    }, 5000); // adjust based on your average reconstruction time

  } catch (error) {
    console.error('Error initiating download:', error);
    setDownloadStatus('Failed to initiate download');
  }
};


  // Toggle peer selection
  const togglePeerSelection = (peerId) => {
    if (selectedPeers.includes(peerId)) {
      setSelectedPeers(selectedPeers.filter(id => id !== peerId));
    } else {
      setSelectedPeers([...selectedPeers, peerId]);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>NetSwarm P2P File Sharing</h1>
        <nav>
          <button 
            className={activeTab === 'dashboard' ? 'active' : ''}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button 
            className={activeTab === 'send' ? 'active' : ''}
            onClick={() => setActiveTab('send')}
          >
            Send File
          </button>
          <button 
            className={activeTab === 'receive' ? 'active' : ''}
            onClick={() => setActiveTab('receive')}
          >
            Receive File
          </button>
        </nav>
      </header>

      <main className="content">
        {activeTab === 'dashboard' && (
          <div className="dashboard">
            <h2>Network Overview</h2>
            <div className="stats">
              <div className="stat-card">
                <h3>{Object.keys(peers).length}</h3>
                <p>Active Peers</p>
              </div>
              <div className="stat-card">
                <h3>{availableFiles.length}</h3>
                <p>Available Files</p>
              </div>
              <div className="stat-card">
                <h3>{Object.values(peers).reduce((acc, peer) => acc + peer.files.length, 0)}</h3>
                <p>Total Chunks</p>
              </div>
            </div>

            <div className="peer-list">
              <h3>Active Peers</h3>
              <div className="peer-grid">
                {Object.entries(peers).map(([peerId, peerInfo]) => (
                  <div key={peerId} className="peer-card">
                    <div className="peer-header">
                      <div className="peer-status"></div>
                      <h4>{peerId}</h4>
                      <span>{peerInfo.ip}:{peerInfo.port}</span>
                    </div>
                    <div className="peer-files">
                      <strong>Files:</strong>
                      <ul>
                        {peerInfo.files.map((file, index) => (
                          <li key={index}>{file}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'send' && (
          <div className="send-file">
            <h2>Send a File</h2>
            <div 
              className={`drop-zone ${isDragging ? 'dragging' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {selectedFile ? (
                <div className="file-info">
                  <div className="file-icon">📄</div>
                  <div className="file-details">
                    <h3>{selectedFile.name}</h3>
                    <p>{(selectedFile.size / 1024).toFixed(2)} KB</p>
                  </div>
                  <button onClick={() => setSelectedFile(null)}>Remove</button>
                </div>
              ) : (
                <>
                  <p>Drag & drop your file here</p>
                  <p>or</p>
                  <input 
                    type="file" 
                    id="file-select" 
                    onChange={handleFileSelect}
                    style={{ display: 'none' }} 
                  />
                  <label htmlFor="file-select" className="browse-btn">
                    Browse Files
                  </label>
                </>
              )}
            </div>
            
            {sendingStatus && <p className="status">{sendingStatus}</p>}
            
            <button 
              className="send-btn"
              onClick={sendFile}
              disabled={!selectedFile}
            >
              Send File
            </button>
          </div>
        )}

        {activeTab === 'receive' && (
          <div className="receive-file">
            <h2>Receive a File</h2>
            
            <div className="file-selection">
              <h3>Available Files</h3>
              <div className="file-grid">
                {availableFiles.map((file, index) => (
                  <div key={index} className="file-card">
                    <div className="file-icon">📄</div>
                    <div className="file-name">{file}</div>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="peer-selection">
              <h3>Select Peers</h3>
              <div className="multi-peer">
                <label>
                  <input 
                    type="checkbox" 
                    checked={useMultiple}
                    onChange={(e) => setUseMultiple(e.target.checked)}
                  />
                  Download from multiple peers
                </label>
              </div>
              
              <div className="peer-grid">
                {Object.entries(peers).map(([peerId, peerInfo]) => (
                  <div 
                    key={peerId} 
                    className={`peer-card ${selectedPeers.includes(peerId) ? 'selected' : ''}`}
                    onClick={() => useMultiple && togglePeerSelection(peerId)}
                  >
                    <div className="peer-header">
                      <div className="peer-status"></div>
                      <h4>{peerId}</h4>
                      <span>{peerInfo.ip}:{peerInfo.port}</span>
                    </div>
                    <div className="peer-files">
                      <strong>Files:</strong>
                      <ul>
                        {peerInfo.files.map((file, index) => (
                          <li key={index}>{file}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            {downloadStatus && <p className="status">{downloadStatus}</p>}
            
            <button 
              className="download-btn"
              onClick={receiveFile}
              disabled={useMultiple && selectedPeers.length === 0}
            >
              Download File
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>NetSwarm P2P File Sharing System</p>
        <div className="system-status">
          <span className="status-dot"></span>
          <span>Bootstrap Server: Active</span>
          <span className="status-dot"></span>
          <span>Chunk Server: Active</span>
        </div>
      </footer>
    </div>
  );
}

export default App;