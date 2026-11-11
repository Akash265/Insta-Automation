// Archive filters (P1-11): show stories matching the text, topic and source filters.
// Works on the server-rendered list; without JavaScript the full archive is shown.
(function () {
  "use strict";
  var form = document.getElementById("filters");
  var list = document.getElementById("archive");
  if (!form || !list) return;
  var q = document.getElementById("q");
  var category = document.getElementById("category");
  var publisher = document.getElementById("publisher");
  var count = document.getElementById("count");
  var issues = Array.prototype.slice.call(list.querySelectorAll(".archive-issue"));

  function apply() {
    var text = q.value.trim().toLowerCase();
    var shown = 0;
    issues.forEach(function (issue) {
      var any = false;
      issue.querySelectorAll("li[data-category]").forEach(function (li) {
        var ok = (!category.value || li.dataset.category === category.value) &&
          (!publisher.value || li.dataset.publisher === publisher.value) &&
          (!text || li.textContent.toLowerCase().indexOf(text) !== -1);
        li.hidden = !ok;
        if (ok) { any = true; shown += 1; }
      });
      issue.hidden = !any;
    });
    count.textContent = shown + (shown === 1 ? " story" : " stories");
  }

  form.hidden = false;
  form.addEventListener("submit", function (e) { e.preventDefault(); });
  [q, category, publisher].forEach(function (el) { el.addEventListener("input", apply); });
  apply();
})();
