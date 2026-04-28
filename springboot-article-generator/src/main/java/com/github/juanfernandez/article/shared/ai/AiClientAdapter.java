package com.github.juanfernandez.article.shared.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.juanfernandez.article.shared.ai.port.AiPort;
import com.github.juanfernandez.article.shared.config.ArticleGeneratorProperties;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.response.ChatResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

/**
 * Infrastructure adapter that implements {@link AiPort} by delegating to the configured
 * AI provider — OpenAI, Google Gemini, Ollama or Anthropic — all routed through
 * LangChain4j when a {@link ChatModel} bean is available.
 *
 * <p>This class lives in the shared infrastructure layer and is consumed by both the
 * article and pregunta bounded contexts through the {@link AiPort} port interface.
 *
 * <h2>Provider routing</h2>
 * <ul>
 *   <li>When a LangChain4j {@link ChatModel} bean is present, all providers are routed
 *       through {@link #callLangChain4j(String, String)} regardless of the configured provider.</li>
 *   <li>Without a {@link ChatModel} bean the service falls back to direct REST calls for
 *       OpenAI, Gemini and Ollama.  Anthropic requires LangChain4j and throws a descriptive
 *       error when no bean is found.</li>
 * </ul>
 */
public class AiClientAdapter implements AiPort {

    private static final Logger log = LoggerFactory.getLogger(AiClientAdapter.class);

    private static final String OPENAI_BASE_URL = "https://api.openai.com";
    private static final String GEMINI_BASE_URL  = "https://generativelanguage.googleapis.com";

    private final ArticleGeneratorProperties properties;
    private final ObjectMapper objectMapper;

    /** Optional LangChain4j chat model — present when a langchain4j starter is configured. */
    private final ChatModel chatModel;

    /**
     * Constructor used when a LangChain4j {@link ChatModel} is available.
     *
     * @param properties   article-generator configuration properties
     * @param objectMapper Jackson mapper for JSON (de)serialisation
     * @param chatModel    LangChain4j chat model (may be {@code null} for Gemini/Ollama-only setups)
     */
    public AiClientAdapter(ArticleGeneratorProperties properties,
                           ObjectMapper objectMapper,
                           ChatModel chatModel) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.chatModel = chatModel;
    }

    /**
     * Backwards-compatible constructor without a LangChain4j model.
     * Falls back to the direct REST client for OpenAI calls.
     *
     * @param properties   article-generator configuration properties
     * @param objectMapper Jackson mapper for JSON (de)serialisation
     */
    public AiClientAdapter(ArticleGeneratorProperties properties, ObjectMapper objectMapper) {
        this(properties, objectMapper, null);
    }

    // ── AiPort implementation ─────────────────────────────────────────────

    /**
     * {@inheritDoc}
     *
     * <p>When a LangChain4j {@link ChatModel} bean is available it is used for <em>all</em>
     * providers (OpenAI, Google Gemini, Ollama, Anthropic).  Otherwise falls back to direct
     * REST calls.
     */
    @Override
    public String generate(String systemMsg, String userPrompt, int maxTokens, double temperature) {
        if (chatModel != null) {
            return callLangChain4j(systemMsg, userPrompt);
        }
        if (isAnthropicProvider()) {
            throw new RuntimeException(
                    "Anthropic provider requires LangChain4j. "
                    + "Add langchain4j-anthropic-spring-boot-starter and configure "
                    + "langchain4j.anthropic.chat-model.api-key in application.yml.");
        }
        if (isGeminiProvider()) {
            return callGemini(systemMsg, userPrompt, maxTokens, temperature);
        } else if (isOllamaProvider()) {
            return callOpenAiCompatible(
                    resolveOllamaBaseUrl(),
                    "ollama",
                    systemMsg, userPrompt, maxTokens, temperature);
        } else {
            return callOpenAiCompatible(
                    OPENAI_BASE_URL,
                    properties.getOpenaiApiKey(),
                    systemMsg, userPrompt, maxTokens, temperature);
        }
    }

    // ── Provider detection ────────────────────────────────────────────────

    /** Returns {@code true} when the active provider is Google Gemini. */
    public boolean isGeminiProvider() {
        AiProvider p = properties.getProvider();
        if (p == AiProvider.GEMINI) return true;
        if (p == AiProvider.OPENAI || p == AiProvider.OLLAMA || p == AiProvider.ANTHROPIC) return false;
        return properties.getModel() != null && properties.getModel().toLowerCase().startsWith("gemini");
    }

    /** Returns {@code true} when the active provider is Ollama. */
    public boolean isOllamaProvider() {
        AiProvider p = properties.getProvider();
        if (p == AiProvider.OLLAMA) return true;
        if (p == AiProvider.OPENAI || p == AiProvider.GEMINI || p == AiProvider.ANTHROPIC) return false;
        String baseUrl = properties.getOllamaBaseUrl();
        return baseUrl != null && !baseUrl.isBlank();
    }

    /** Returns {@code true} when the active provider is Anthropic. */
    public boolean isAnthropicProvider() {
        return properties.getProvider() == AiProvider.ANTHROPIC;
    }

    // ── JSON extraction ───────────────────────────────────────────────────

    // JSON extraction and parsing are provided by the shared JsonUtils bean.
    // AiClientAdapter focuses solely on transport: calling the AI provider and
    // returning the raw text response.

    // ── LangChain4j ───────────────────────────────────────────────────────

    private String callLangChain4j(String systemMsg, String userPrompt) {
        log.debug("Calling AI provider via LangChain4j ChatModel");
        try {
            ChatResponse response = chatModel.chat(
                    SystemMessage.from(systemMsg),
                    UserMessage.from(userPrompt));
            String content = response.aiMessage().text();
            if (content == null || content.isBlank()) {
                throw new RuntimeException("LangChain4j returned an empty response.");
            }
            return content;
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("LangChain4j call failed: " + e.getMessage(), e);
        }
    }

    // ── OpenAI / Ollama ───────────────────────────────────────────────────

    private String callOpenAiCompatible(String baseUrl, String apiKey,
                                         String systemMsg, String userPrompt,
                                         int maxTokens, double temperature) {
        RestClient client = RestClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                .build();

        Map<String, Object> requestBody = Map.of(
                "model", properties.getModel(),
                "messages", List.of(
                        Map.of("role", "system", "content", systemMsg),
                        Map.of("role", "user", "content", userPrompt)
                ),
                "max_tokens", maxTokens,
                "temperature", temperature
        );

        log.debug("Calling OpenAI-compatible API at {} with model={}", baseUrl, properties.getModel());

        try {
            String responseBody = client.post()
                    .uri("/v1/chat/completions")
                    .body(requestBody)
                    .retrieve()
                    .body(String.class);

            return extractOpenAiContent(responseBody);
        } catch (Exception e) {
            throw new RuntimeException("AI API call failed (" + baseUrl + "): " + e.getMessage(), e);
        }
    }

    private String extractOpenAiContent(String responseBody) {
        try {
            JsonNode root = objectMapper.readTree(responseBody);
            JsonNode content = root.path("choices").path(0).path("message").path("content");
            if (content.isMissingNode() || content.isNull()) {
                throw new RuntimeException("AI response contained no content. Response: "
                        + responseBody.substring(0, Math.min(300, responseBody.length())));
            }
            return content.asText();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse AI response: " + e.getMessage(), e);
        }
    }

    // ── Google Gemini ─────────────────────────────────────────────────────

    private String callGemini(String systemMsg, String userPrompt, int maxTokens, double temperature) {
        String apiKey = properties.getGeminiApiKey();
        if (apiKey == null || apiKey.isBlank()) {
            throw new RuntimeException(
                    "article-generator.gemini-api-key is not configured. "
                    + "Set it in application.properties or via the GEMINI_API_KEY environment variable.");
        }

        RestClient client = RestClient.builder()
                .baseUrl(GEMINI_BASE_URL)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .build();

        Map<String, Object> requestBody = Map.of(
                "contents", List.of(
                        Map.of("role", "user",
                               "parts", List.of(Map.of("text", userPrompt)))
                ),
                "systemInstruction", Map.of(
                        "parts", List.of(Map.of("text", systemMsg))
                ),
                "generationConfig", Map.of(
                        "maxOutputTokens", maxTokens,
                        "temperature", temperature
                )
        );

        String uri = "/v1beta/models/" + properties.getModel() + ":generateContent?key=" + apiKey;
        log.debug("Calling Gemini API with model={}", properties.getModel());

        try {
            String responseBody = client.post()
                    .uri(uri)
                    .body(requestBody)
                    .retrieve()
                    .body(String.class);

            return extractGeminiContent(responseBody);
        } catch (Exception e) {
            throw new RuntimeException("Gemini API call failed: " + e.getMessage(), e);
        }
    }

    private String extractGeminiContent(String responseBody) {
        try {
            JsonNode root = objectMapper.readTree(responseBody);
            JsonNode text = root.path("candidates").path(0)
                    .path("content").path("parts").path(0).path("text");
            if (text.isMissingNode() || text.isNull()) {
                throw new RuntimeException("Gemini response contained no text. Response: "
                        + responseBody.substring(0, Math.min(300, responseBody.length())));
            }
            return text.asText();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse Gemini response: " + e.getMessage(), e);
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private String resolveOllamaBaseUrl() {
        String url = properties.getOllamaBaseUrl();
        if (url == null || url.isBlank()) {
            url = "http://localhost:11434";
        }
        return url.replaceAll("/v1/?$", "");
    }
}
