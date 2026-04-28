package com.github.juanfernandez.article.pregunta.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.github.juanfernandez.article.pregunta.domain.Pregunta;
import com.github.juanfernandez.article.pregunta.port.in.PreguntaGeneratorPort;
import com.github.juanfernandez.article.pregunta.port.out.PreguntaRepositoryPort;
import com.github.juanfernandez.article.shared.ai.port.AiPort;
import com.github.juanfernandez.article.shared.util.JsonUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Application service that implements the {@link PreguntaGeneratorPort} use case.
 *
 * <p>Reads all existing questions from the {@code preguntas} table via {@link PreguntaRepositoryPort},
 * uses the configured AI provider via {@link AiPort} to generate a new unique multilingual question
 * (Catalan, English, Spanish, French), and persists it.
 *
 * <p>The AI is asked to return a JSON object with the following structure:
 * <pre>{@code
 * {
 *   "campo": "camelCaseIdentifier",
 *   "texto": {
 *     "ca": "Pregunta en català",
 *     "en": "Question in English",
 *     "es": "Pregunta en español",
 *     "fr": "Question en français"
 *   }
 * }
 * }</pre>
 *
 * <p>Example usage from a consuming Spring Boot application:
 * <pre>{@code
 * @Autowired
 * private PreguntaGeneratorPort preguntaGeneratorPort;
 *
 * Pregunta nueva = preguntaGeneratorPort.generateAndSave();
 * }</pre>
 */
public class PreguntaGeneratorService implements PreguntaGeneratorPort {

    private static final Logger log = LoggerFactory.getLogger(PreguntaGeneratorService.class);

    /** Maximum number of existing Spanish question texts included in the AI prompt. */
    private static final int MAX_CONTEXT_QUESTIONS = 100;

    private static final String SYSTEM_MSG =
            "Eres un experto en declaraciones de la renta (IRPF) y generas preguntas para un asistente fiscal. "
            + "Tu tarea es crear UNA NUEVA pregunta en cuatro idiomas (ca, en, es, fr) que NO exista ya en la lista "
            + "proporcionada. "
            + "Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta, sin texto adicional:\n"
            + "{\n"
            + "  \"campo\": \"camelCaseIdentifier\",\n"
            + "  \"texto\": {\n"
            + "    \"ca\": \"...\",\n"
            + "    \"en\": \"...\",\n"
            + "    \"es\": \"...\",\n"
            + "    \"fr\": \"...\"\n"
            + "  }\n"
            + "}";

    private final AiPort aiPort;
    private final JsonUtils jsonUtils;
    private final PreguntaRepositoryPort preguntaRepository;

    public PreguntaGeneratorService(AiPort aiPort, PreguntaRepositoryPort preguntaRepository,
                                     JsonUtils jsonUtils) {
        this.aiPort = aiPort;
        this.jsonUtils = jsonUtils;
        this.preguntaRepository = preguntaRepository;
    }

    // ── PreguntaGeneratorPort implementation ──────────────────────────────

    /**
     * {@inheritDoc}
     */
    @Override
    public Pregunta generateAndSave() {
        List<Pregunta> existing = preguntaRepository.findAllByOrderByOrdenAsc();
        log.info("Generating new question. Existing questions in DB: {}", existing.size());

        String prompt = buildPrompt(existing);

        String rawResponse = aiPort.generate(SYSTEM_MSG, prompt, 400, 0.8);
        String jsonBlock   = extractJsonBlock(rawResponse);
        JsonNode data      = safeJsonParse(jsonBlock);

        String campo = textNode(data, "campo");
        if (campo.isBlank()) {
            throw new RuntimeException(
                    "AI response is missing the 'campo' field. Raw response preview: "
                    + rawResponse.substring(0, Math.min(300, rawResponse.length())));
        }

        JsonNode textoNode = data.path("texto");
        if (textoNode.isMissingNode() || !textoNode.isObject()) {
            throw new RuntimeException(
                    "AI response is missing the 'texto' object. Raw response preview: "
                    + rawResponse.substring(0, Math.min(300, rawResponse.length())));
        }

        Map<String, String> texto = new LinkedHashMap<>();
        for (String lang : new String[]{"ca", "en", "es", "fr"}) {
            String val = textoNode.path(lang).asText("").strip();
            if (val.isBlank()) {
                throw new RuntimeException(
                        "AI response is missing the '" + lang + "' translation in 'texto'. "
                        + "Raw response preview: "
                        + rawResponse.substring(0, Math.min(300, rawResponse.length())));
            }
            texto.put(lang, val);
        }

        if (preguntaRepository.existsByCampo(campo)) {
            throw new RuntimeException(
                    "AI generated a 'campo' that already exists in the database: \"" + campo + "\"");
        }

        String generatedEs = texto.get("es");
        boolean textDuplicate = existing.stream()
                .map(p -> p.getTexto() != null ? p.getTexto().get("es") : null)
                .filter(t -> t != null)
                .anyMatch(t -> t.equalsIgnoreCase(generatedEs));
        if (textDuplicate) {
            throw new RuntimeException(
                    "AI generated a Spanish question text that already exists: \"" + generatedEs + "\"");
        }

        int nextOrden = existing.stream()
                .map(Pregunta::getOrden)
                .filter(o -> o != null)
                .max(Integer::compareTo)
                .map(max -> max + 1)
                .orElse(1);

        Pregunta nueva = new Pregunta(campo, nextOrden, texto);
        Pregunta saved = preguntaRepository.save(nueva);
        log.info("New question saved: id={}, campo='{}', orden={}, es='{}'",
                saved.getId(), saved.getCampo(), saved.getOrden(), texto.get("es"));
        return saved;
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private String buildPrompt(List<Pregunta> existing) {
        StringBuilder sb = new StringBuilder();

        if (existing.isEmpty()) {
            sb.append("No hay preguntas registradas todavía. Crea la primera pregunta para el asistente fiscal del IRPF.");
        } else {
            sb.append("Las siguientes preguntas YA EXISTEN en el cuestionario fiscal (campo: texto en español). "
                    + "NO puedes repetir ninguna de ellas ni crear algo semánticamente equivalente:\n\n");
            existing.stream()
                    .limit(MAX_CONTEXT_QUESTIONS)
                    .forEach(p -> {
                        String es = p.getTexto() != null ? p.getTexto().get("es") : "";
                        sb.append("- ").append(p.getCampo()).append(": ").append(es).append("\n");
                    });
            sb.append("\nGenera UNA NUEVA pregunta diferente a todas las anteriores, "
                    + "relevante para la declaración de la renta española (IRPF).");
        }

        return sb.toString();
    }

    private String extractJsonBlock(String text) {
        return jsonUtils.extractJsonBlock(text);
    }

    private JsonNode safeJsonParse(String json) {
        return jsonUtils.safeJsonParse(json);
    }

    private static String textNode(JsonNode node, String field) {
        JsonNode n = node.path(field);
        return n.isMissingNode() || n.isNull() ? "" : n.asText("").strip();
    }
}
