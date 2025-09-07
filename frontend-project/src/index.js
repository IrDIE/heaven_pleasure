function formatDateTime(input) {
  if (!input) return '';
  // SQLite обычно шлёт "YYYY-MM-DD HH:MM:SS" — вытащим как есть
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(String(input));
  if (m) return `${m[1]} ${m[2]}:${m[3]}:${m[4]}`;

  // Фолбэк: парсим любым браузерным Date и нормализуем
  const d = new Date(input);
  if (isNaN(d.getTime())) return String(input);
  const z = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth()+1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
}

// --- AUTH STATE ---
function isAuthorized() {
  return localStorage.getItem("authorized") === "true";
}

function authorizeUser() {
  localStorage.setItem("authorized", "true");
}

function logoutUser() {
  localStorage.removeItem("authorized");

}
async function loadReviewHistory() {
  const user = JSON.parse(localStorage.getItem('user') || '{}');

  if (!user.username) {
    console.error('No user logged in');
    return;
  }

  try {
    const response = await fetch(`/api/user-projects?username=${user.username}`);
    const data = await response.json();

    if (data.success) {
      updateReviewHistoryTable(data.projects);
    } else {
      console.error('Failed to load review history:', data.message);
    }
  } catch (error) {
    console.error('Error loading review history:', error);
  }
}

function updateReviewHistoryTable(projects) {
  const tbody = document.querySelector('#review-history-table tbody');

  if (!tbody) {
    console.error('Review history table not found');
    return;
  }

  // Clear existing rows (except the first one if it's a placeholder)
  tbody.innerHTML = '';

  if (projects.length === 0) {
    // Add a placeholder row if no projects
    const placeholderRow = document.createElement('tr');
    placeholderRow.innerHTML = `
            <td colspan="4" class="px-6 py-4 text-center text-surface-400">
                No projects yet. Upload your first project to get started!
            </td>
        `;
    tbody.appendChild(placeholderRow);
    return;
  }

  // Add rows for each project
  projects.forEach(project => {
    const row = document.createElement('tr');
    row.className = 'hover:bg-surface-800/70 transition-colors';

    // Format date
    const formattedDate = project.created_at_hms || formatDateTime(project.created_at);

    // Determine status badge
    let statusBadge = '';
    if (project.status === 'completed') {
      statusBadge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400">Completed</span>';
    } else if (project.status === 'in_review') {
      statusBadge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400">In Progress</span>';
    } else if (project.status === 'uploaded') {
      statusBadge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-green-400">Uploaded</span>';
    } else {
      statusBadge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-400">Pending</span>';
    }

    // Determine action button
    let actionButton = '';
    if (project.status === 'completed') {
      actionButton = `<button onclick="viewReport(${project.id})" class="font-medium text-primary-400 hover:text-primary-300 transition-colors">View Report</button>`;
    } else if (project.status === 'in_review') {
      actionButton = '<button class="font-medium text-surface-400 cursor-not-allowed" disabled>Processing...</button>';
    } else {
      actionButton = '<button class="font-medium text-primary-400 hover:text-primary-300 transition-colors">View Details</button>';
    }

    row.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-surface-400">${formattedDate}</td>
            <td class="px-6 py-4 whitespace-nowrap text-surface-400">${project.review_type || 'System'} Review</td>
            <td class="px-6 py-4 whitespace-nowrap">${statusBadge}</td>
            <td class="px-6 py-4 whitespace-nowrap text-right">${actionButton}</td>
        `;

    tbody.appendChild(row);
  });
}

function viewReport(projectId) {
  window.open(`/api/review-report/${projectId}`, '_blank');
}

// --- main PAGE LOGIC ---
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;

  // --- Redirects ---
  if (path.endsWith("index") && isAuthorized()) {
    window.location.href = "main_page";
    return;
  }

  // Prevent access to main_page if not authorized
  if (path.endsWith("main_page") && !isAuthorized()) {
    // Not logged in → kick back to login
    window.location.href = "index";
    return;
  }

  if (path.endsWith("main_page") || window.location.pathname === '/main-page.html') {
    loadReviewHistory();
  }

  // --- Login form handling (on index.html) ---
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      // (Optional) You could validate inputs here
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();
      try {
        const response = await fetch('http://localhost:5000/api/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (data.success) {
          if (username && password) {
            // Store user data in localStorage
            localStorage.setItem('user', JSON.stringify(data.user));
            // Redirect to main page
            authorizeUser();
            window.location.href = "main_page"; // Redirect to main_page.html
            return;

          } else {
            alert("Please enter username and password");
          }

        } else {
          alert('Login failed: ' + data.message);
        }

      } catch (error) {
        console.error('Error:', error);
        alert('An error occurred during login');
      } finally {
        loginBtn.textContent = 'Log in';
        loginBtn.disabled = false;
      }
    });
  }

  // --- Logout handling (on main_page.html) ---
  const logoutBtn = document.getElementById("logoutBtn");
  if (path.endsWith("main_page") && logoutBtn) {
    logoutBtn.addEventListener("click", (e) => {
      e.preventDefault();
      logoutUser();
      window.location.href = "index"; // go back to login page
      return;
    });
  }

  // --- Sign up link handling (on index.html) ---
  const signupLink = document.getElementById("signup-link");
  if (path.endsWith("index") && signupLink) {
    signupLink.addEventListener("click", (e) => {
      e.preventDefault(); // Prevent default anchor behavior
      signupLink.href = "create-account"; // Set the href attribute

      window.location.href = "create-account"; // Redirect to create-account.html
      return;
    });
  }
  /// --- Back to login from create-account.html ---
  const signupLinkFromCreate = document.getElementById("login-link");
  if (path.endsWith("create-account") && signupLinkFromCreate) {
    signupLinkFromCreate.addEventListener("click", (e) => {
      e.preventDefault(); // Prevent default anchor behavior
      signupLinkFromCreate.href = "index"; // Set the href attribute

      window.location.href = "index"; // Redirect to create-account.html
      return;
    });
  }
  //// --- create new user
  const signupBtn = document.getElementById("signup-btn");
  if (signupBtn) {
    signupBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();
      try {
        const response = await fetch('http://localhost:5000/api/create-account', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (data.success) {
          if (username && password) {
            // Store user data in localStorage
            localStorage.setItem('user', JSON.stringify(data.user));
            // Redirect to main page
            authorizeUser();
            window.location.href = "main_page"; // Redirect to main_page.html
            return;

          } else {
            alert("Please enter username and password");
          }

        } else {
          alert('Login failed: You need to create account first' + data.message);
        }

      } catch (error) {
        console.error('Error:', error);
        alert('An error occurred during login');
      } finally {
        loginBtn.textContent = 'Log in';
        loginBtn.disabled = false;
      }

      // authorizeUser();
      // window.location.href = "main_page"; // Redirect to main_page.html
      // return;
    });
  }

});

/// ----- UPLOAD PROGECT LOGIC STARTS HERE -----
// Upload Project Modal functionality
document.addEventListener('DOMContentLoaded', function () {
  // Get elements

  const uploadButton = document.getElementById('UploadBtn');
  const uploadModal = document.getElementById('upload-modal');
  const closeModalButton = document.getElementById('close-modal');
  const cancelUploadButton = document.getElementById('cancel-upload');
  const tabFileButton = document.getElementById('tab-file');
  const tabLinkButton = document.getElementById('tab-link');
  const fileUploadForm = document.getElementById('file-upload-form');
  const linkUploadForm = document.getElementById('link-upload-form');
  const fileInput = document.getElementById('file-input');
  const fileList = document.getElementById('file-list');
  const selectedFilesList = document.getElementById('selected-files');
  const submitButton = document.getElementById('submit-upload');

  // Open modal when Upload Project button is clicked
  if (uploadButton) {
    uploadButton.addEventListener('click', function () {
      uploadModal.classList.remove('hidden');
      resetForms();
    });
  }

  // Close modal functions
  function closeModal() {
    uploadModal.classList.add('hidden');
  }

  if (closeModalButton) closeModalButton.addEventListener('click', closeModal);
  if (cancelUploadButton) cancelUploadButton.addEventListener('click', closeModal);

  // Close modal when clicking outside
  uploadModal.addEventListener('click', function (e) {
    if (e.target === uploadModal) {
      closeModal();
    }
  });

  // Tab switching functionality
  if (tabFileButton && tabLinkButton) {
    tabFileButton.addEventListener('click', function () {
      activateTab('file');
    });

    tabLinkButton.addEventListener('click', function () {
      activateTab('link');
    });
  }

  function activateTab(tabName) {
    // Update tab buttons
    if (tabName === 'file') {
      tabFileButton.classList.add('bg-surface-800', 'text-primary-400', 'border-b-2', 'border-primary-400');
      tabFileButton.classList.remove('text-surface-400');
      tabLinkButton.classList.remove('bg-surface-800', 'text-primary-400', 'border-b-2', 'border-primary-400');
      tabLinkButton.classList.add('text-surface-400');

      // Show file form, hide link form
      fileUploadForm.classList.remove('hidden');
      linkUploadForm.classList.add('hidden');

      // Update submit button text
      submitButton.textContent = 'Upload Files';
    } else {
      tabLinkButton.classList.add('bg-surface-800', 'text-primary-400', 'border-b-2', 'border-primary-400');
      tabLinkButton.classList.remove('text-surface-400');
      tabFileButton.classList.remove('bg-surface-800', 'text-primary-400', 'border-b-2', 'border-primary-400');
      tabFileButton.classList.add('text-surface-400');

      // Show link form, hide file form
      linkUploadForm.classList.remove('hidden');
      fileUploadForm.classList.add('hidden');

      // Update submit button text
      submitButton.textContent = 'Submit Link';
    }
  }

  // File input handling
  if (fileInput) {
    fileInput.addEventListener('change', function () {
      const files = fileInput.files;
      if (files.length > 0) {
        selectedFilesList.innerHTML = '';

        for (let i = 0; i < files.length; i++) {
          const listItem = document.createElement('li');
          listItem.textContent = files[i].name;
          listItem.className = 'text-sm';
          selectedFilesList.appendChild(listItem);
        }

        fileList.classList.remove('hidden');
      } else {
        fileList.classList.add('hidden');
      }
    });
  }

  // Submit form handling
  if (submitButton) {
    submitButton.addEventListener('click', function () {
      if (fileUploadForm.classList.contains('hidden')) {
        // Handle link submission
        handleLinkSubmission();
      } else {
        // Handle file upload
        handleFileUpload();
      }
    });
  }

  // Reset forms to initial state
  function resetForms() {
    // Reset file form
    fileInput.value = '';
    fileList.classList.add('hidden');
    document.getElementById('project-name').value = '';
    document.getElementById('project-description').value = '';

    // Reset link form
    document.getElementById('project-link').value = '';
    document.getElementById('link-project-name').value = '';
    document.getElementById('link-project-description').value = '';

    // Activate file tab by default
    activateTab('file');
  }

  // Handle file upload to backend
  async function handleFileUpload() {
    const files = fileInput.files;
    const projectName = document.getElementById('project-name').value;
    const description = document.getElementById('project-description').value;

    // Validate inputs
    if (files.length === 0) {
      alert('Please select at least one file to upload.');
      return;
    }

    if (!projectName) {
      alert('Please enter a project name.');
      return;
    }

    // Create FormData object to send files and metadata
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    formData.append('project_name', projectName);
    formData.append('description', description);
    formData.append('type', 'file');

    // Get user info from localStorage
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    if (user.username) {
      formData.append('username', user.username);
    }

    // Show loading state
    submitButton.disabled = true;
    submitButton.textContent = 'Uploading...';

    try {
      const response = await fetch('/api/upload-project', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.success) {
        alert('Project uploaded successfully!');
        closeModal();
        // Refresh the review history
        loadReviewHistory();
      } else {
        alert('Error: ' + data.message);
      }
    } catch (error) {
      console.error('Upload error:', error);
      alert('An error occurred during upload. Please try again.');
    } finally {
      // Reset button state
      submitButton.disabled = false;
      submitButton.textContent = 'Upload Files';
    }
  }

  // Handle link submission to backend
  async function handleLinkSubmission() {
    const projectLink = document.getElementById('project-link').value;
    const projectName = document.getElementById('link-project-name').value;
    const description = document.getElementById('link-project-description').value;

    // Validate inputs
    if (!projectLink) {
      alert('Please enter a project URL.');
      return;
    }

    if (!projectName) {
      alert('Please enter a project name.');
      return;
    }

    // Get user info from localStorage
    const user = JSON.parse(localStorage.getItem('user') || '{}');

    // Prepare data for submission
    const submissionData = {
      project_url: projectLink,
      project_name: projectName,
      description: description,
      type: 'link',
      username: user.username || ''
    };

    // Show loading state
    submitButton.disabled = true;
    submitButton.textContent = 'Submitting...';

    try {
      const response = await fetch('/api/upload-project', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(submissionData)
      });

      const data = await response.json();

      if (data.success) {
        alert('Project link submitted successfully!');
        closeModal();
        // Refresh the review history
        loadReviewHistory();
      } else {
        alert('Error: ' + data.message);
      }
    } catch (error) {
      console.error('Submission error:', error);
      alert('An error occurred during submission. Please try again.');
    } finally {
      // Reset button state
      submitButton.disabled = false;
      submitButton.textContent = 'Submit Link';
    }
  }
});
/// ----- UPLOAD PROGECT LOGIC ENDS HERE -----

// Handle Send for Review button
document.addEventListener('DOMContentLoaded', function () {
  const sendForReviewButton = document.getElementById('sendReviewBtn');

  if (sendForReviewButton) {
    sendForReviewButton.addEventListener('click', async function () {
      const user = JSON.parse(localStorage.getItem('user') || '{}');

      if (!user.username) {
        alert('Please log in first');
        return;
      }

      // Show loading state
      const originalText = sendForReviewButton.innerHTML;
      sendForReviewButton.innerHTML = '<span class="material-symbols-outlined">hourglass_top</span><span>Sending...</span>';
      sendForReviewButton.disabled = true;

      try {
        const response = await fetch('/api/send-for-review', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ username: user.username })
        });

        const data = await response.json();

        if (data.success) {
          alert('Project sent for review successfully! It may take a few minutes to complete.');
          // Refresh the review history
          loadReviewHistory();

          // Start polling for review completion
          startReviewStatusPolling(data.project_id);
        } else {
          alert('Error: ' + data.message);
        }
      } catch (error) {
        console.error('Send for review error:', error);
        alert('An error occurred while sending for review. Please try again.');
      } finally {
        // Reset button state
        sendForReviewButton.innerHTML = originalText;
        sendForReviewButton.disabled = false;
      }
    });
  }
});

// Poll for review completion
function startReviewStatusPolling(projectId) {
  let attempts = 0;
  const maxAttempts = 30; // 5 minutes (10-second intervals)

  const pollInterval = setInterval(async () => {
    attempts++;

    if (attempts > maxAttempts) {
      clearInterval(pollInterval);
      console.log('Polling stopped after maximum attempts');
      return;
    }

    try {
      const response = await fetch(`/api/user-projects?username=${encodeURIComponent(JSON.parse(localStorage.getItem('user') || '{}').username)}`);
      const data = await response.json();

      if (data.success) {
        const project = data.projects.find(p => p.id === projectId);

        if (project && project.status === 'completed') {
          clearInterval(pollInterval);
          // Refresh the review history to show completed status
          loadReviewHistory();
          alert('Review completed! Check your review history for the report.');
        }
      }
    } catch (error) {
      console.error('Polling error:', error);
    }
  }, 10000); // Check every 10 seconds
}

