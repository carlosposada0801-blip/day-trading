const form = document.querySelector("form");
if (form.dataset["2fa"] === "1") document.getElementById("code-row").hidden = false;
const e = new URLSearchParams(location.search).get("error");
if (e) {
  document.getElementById("err").textContent = e === "locked"
    ? "Too many attempts. Try again in 15 minutes."
    : form.dataset["2fa"] === "1" ? "Wrong password or code." : "Wrong password.";
}
