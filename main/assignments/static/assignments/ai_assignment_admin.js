(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') {
      fn();
      return;
    }
    document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    var promptField = document.getElementById('id_ai_prompt');
    var pointsField = document.getElementById('id_ai_total_points');
    var generatedField = document.getElementById('id_ai_generated');
    var contentField = document.getElementById('id_ai_content');
    var sectionSubjectField = document.getElementById('id_section_subject');
    var titleField = document.getElementById('id_title');
    var descField = document.getElementById('id_description');
    var totalPointsField = document.getElementById('id_total_points');

    if (!promptField || !sectionSubjectField) return;

    if (!generatedField) {
      generatedField = document.createElement('input');
      generatedField.type = 'hidden';
      generatedField.id = 'id_ai_generated';
      generatedField.name = 'ai_generated';
      var form = document.querySelector('form');
      if (form) form.appendChild(generatedField);
    }
    if (!contentField) {
      contentField = document.createElement('input');
      contentField.type = 'hidden';
      contentField.id = 'id_ai_content';
      contentField.name = 'ai_content';
      var form2 = document.querySelector('form');
      if (form2) form2.appendChild(contentField);
    }

    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'button';
    button.style.marginTop = '8px';
    button.textContent = 'Generate AI Draft';

    promptField.parentElement.appendChild(button);

    button.addEventListener('click', function () {
      var prompt = promptField.value.trim();
      var sectionSubject = sectionSubjectField.value;
      var totalPoints = pointsField ? pointsField.value : '';

      if (!prompt || !sectionSubject) {
        alert('Please fill Section Subject and AI Prompt.');
        return;
      }

      var formData = new FormData();
      formData.append('prompt', prompt);
      formData.append('section_subject', sectionSubject);
      if (totalPoints) {
        formData.append('total_points', totalPoints);
      }

      var parts = window.location.pathname.split('/').filter(Boolean);
      var baseParts = parts.slice(0, 3);
      var url = '/' + baseParts.join('/') + '/ai-generate/';

      button.disabled = true;
      button.textContent = 'Generating...';

      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': window.CSRF_TOKEN || getCookie('csrftoken') || '' },
        body: formData,
      })
        .then(function (response) { return response.json().then(function (data) { return { ok: response.ok, data: data }; }); })
        .then(function (result) {
          if (!result.ok) {
            var detail = result.data && (result.data.detail || result.data.error);
            alert(detail || 'AI generation failed.');
            return;
          }
          var bodyText = result.data.description || '';
          if (!bodyText || !bodyText.trim()) {
            alert('AI returned empty content. Please try again.');
            return;
          }
          if (titleField) titleField.value = result.data.title || '';
          if (descField) descField.value = bodyText;
          if (descField) {
            var event = new Event('input', { bubbles: true });
            descField.dispatchEvent(event);
          }
          if (totalPointsField && result.data.total_points) {
            totalPointsField.value = result.data.total_points;
          }
          if (generatedField) generatedField.value = '1';
          if (contentField) contentField.value = bodyText;
          alert('AI draft generated. Review and click Save when ready.');
        })
        .catch(function () {
          alert('AI generation failed.');
        })
        .finally(function () {
          button.disabled = false;
          button.textContent = 'Generate AI Draft';
        });
    });
  });

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    if (match) return match[2];
    return '';
  }
})();
