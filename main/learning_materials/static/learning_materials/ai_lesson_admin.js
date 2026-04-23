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
    var typeField = document.getElementById('id_ai_type');
    var linkField = document.getElementById('id_ai_link');
    var generatedField = document.getElementById('id_ai_generated');
    var contentField = document.getElementById('id_ai_content');
    var sectionSubjectField = document.getElementById('id_section_subject');
    var titleField = document.getElementById('id_title');
    var descField = document.getElementById('id_description');
    var fileUrlField = document.getElementById('id_file_url');
    var lessonTypeField = document.getElementById('id_type');

    if (!promptField || !typeField || !sectionSubjectField) return;

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
    button.textContent = 'Generate AI Material Draft';

    promptField.parentElement.appendChild(button);

    button.addEventListener('click', function () {
      var prompt = promptField.value.trim();
      var lessonType = typeField.value;
      var sectionSubject = sectionSubjectField.value;
      var fileUrl = linkField ? linkField.value.trim() : '';

      if (!prompt || !lessonType || !sectionSubject) {
        alert('Please fill Section Subject, AI Type, and AI Prompt.');
        return;
      }

      var formData = new FormData();
      formData.append('prompt', prompt);
      formData.append('type', lessonType);
      formData.append('section_subject', sectionSubject);
      if (fileUrl) {
        formData.append('file_url', fileUrl);
      }

      var parts = window.location.pathname.split('/').filter(Boolean);
      // Expected: admin / learning_materials / learningmaterial / (add|<id>) / (change)?
      var baseParts = parts.slice(0, 3); // admin, learning_materials, learningmaterial
      var url = '/' + baseParts.join('/') + '/ai-generate/';

      button.disabled = true;
      button.textContent = 'Generating...';

      function extractLessonText(raw) {
        if (!raw) return '';
        var text = String(raw);
        if (text.indexOf('"content"') === -1 && text.indexOf('"description"') === -1) {
          return text;
        }
        var descMatch = text.match(/\"description\"\s*:\s*\"/);
        var contentMatch = text.match(/\"content\"\s*:\s*\"/);
        var description = '';
        var content = '';
        if (descMatch) {
          var descStart = descMatch.index + descMatch[0].length;
          var descEnd = contentMatch ? contentMatch.index : text.length;
          description = text.slice(descStart, descEnd).trim().replace(/^\s*,/, '').replace(/\"$/, '');
        }
        if (contentMatch) {
          var contentStart = contentMatch.index + contentMatch[0].length;
          content = text.slice(contentStart).trim();
          content = content.replace(/\"\s*}\s*$/, '');
        }
        var combined = [description, content].filter(Boolean).join('\n\n');
        combined = combined.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\"/g, '"').trim();
        return combined || text;
      }

      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': window.CSRF_TOKEN || getCookie('csrftoken') || '' },
        body: formData,
      })
        .then(function (response) { return response.json().then(function (data) { return { ok: response.ok, data: data }; }); })
        .then(function (result) {
          if (!result.ok) {
            var detail = result.data && (result.data.detail || result.data.error);
            alert(detail || 'AI learning material generation failed.');
            return;
          }
          var bodyText = result.data.body || result.data.description || result.data.content || '';
          bodyText = extractLessonText(bodyText);
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
          if (fileUrlField && result.data.file_url) fileUrlField.value = result.data.file_url;
          if (lessonTypeField) lessonTypeField.value = result.data.type || lessonTypeField.value;
          if (generatedField) generatedField.value = '1';
          if (contentField) contentField.value = bodyText;
          alert('AI material draft generated. Review and click Save when ready.');
        })
        .catch(function () {
          alert('AI learning material generation failed.');
        })
        .finally(function () {
          button.disabled = false;
          button.textContent = 'Generate AI Material Draft';
        });
    });
  });

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    if (match) return match[2];
    return '';
  }
})();
