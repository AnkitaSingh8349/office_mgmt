document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("loginForm");
    const loginAlert = document.getElementById("loginAlert");

    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            // clear alerts
            loginAlert.classList.add("d-none");
            loginAlert.innerText = "";

            const formData = new FormData(loginForm);
            
            try {
                const response = await fetch(loginForm.action, {
                    method: "POST",
                    body: formData,
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.redirect) {
                        window.location.href = data.redirect;
                    } else {
                        // Fallback if no redirect provided
                        window.location.href = "/go_employee";
                    }
                } else {
                    // Try to get error message
                    let errorMsg = "Login failed";
                    try {
                        const errData = await response.json();
                        if (errData.error) errorMsg = errData.error;
                        else if (errData.detail) errorMsg = errData.detail;
                    } catch (e2) {
                        console.error("Non-JSON error response", e2);
                    }
                    
                    loginAlert.innerText = errorMsg;
                    loginAlert.classList.remove("d-none");
                }
            } catch (err) {
                console.error(err);
                loginAlert.innerText = "Network error. Please try again.";
                loginAlert.classList.remove("d-none");
            }
        });
    }
});
