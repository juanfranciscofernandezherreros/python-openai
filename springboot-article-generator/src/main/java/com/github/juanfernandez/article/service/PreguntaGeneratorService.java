package com.github.juanfernandez.article.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.github.juanfernandez.article.model.Pregunta;
import com.github.juanfernandez.article.repository.PreguntaRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Service that reads all existing questions from the {@code preguntas} PostgreSQL table,
 * uses the configured AI provider to generate a new unique multilingual question
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
 * private PreguntaGeneratorService preguntaGeneratorService;
 *
 * // Generate and save a new question
 * Pregunta nueva = preguntaGeneratorService.generateAndSave();
 * }</pre>
 *
 * <p>This bean is only registered when both {@code spring-boot-starter-data-jpa}
 * and a {@link PreguntaRepository} are on the classpath (conditional on
 * {@code @ConditionalOnBean(PreguntaRepository.class)} in the auto-configuration).
 */
public class PreguntaGeneratorService {

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

    private final AiClientService aiClient;
    private final PreguntaRepository preguntaRepository;

    public PreguntaGeneratorService(AiClientService aiClient,
                                    PreguntaRepository preguntaRepository) {
        this.aiClient           = aiClient;
        this.preguntaRepository = preguntaRepository;
    }

    // ── Public API ────────────────────────────────────────────────────────

    /**
     * Fetches all questions from the database, asks the AI to generate a new one that does not
     * already exist, saves it, and returns the persisted {@link Pregunta}.
     *
     * <p>The new question is assigned {@code orden = max(orden) + 1}. If the table is empty
     * the question receives {@code orden = 1}.
     *
     * @return the newly created and persisted {@link Pregunta}
     * @throws RuntimeException if the AI returns an invalid or empty response
     * @throws RuntimeException if the AI generates a {@code campo} that already exists in the database
     * @throws RuntimeException if the AI omits any of the required language keys (ca, en, es, fr)
     */
    public Pregunta generateAndSave() {
        List<Pregunta> existing = preguntaRepository.findAllByOrderByOrdenAsc();
        log.info("Generating new question. Existing questions in DB: {}", existing.size());

        String prompt = buildPrompt(existing);

        String rawResponse = aiClient.generate(SYSTEM_MSG, prompt, 400, 0.8);
        String jsonBlock   = aiClient.extractJsonBlock(rawResponse);
        JsonNode data      = aiClient.safeJsonParse(jsonBlock);

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

        // Deduplication: check both campo identifier and Spanish text
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

    private static String textNode(JsonNode node, String field) {
        JsonNode n = node.path(field);
        return n.isMissingNode() || n.isNull() ? "" : n.asText("").strip();
    }
}
