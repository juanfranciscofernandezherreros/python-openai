package com.github.juanfernandez.article.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.juanfernandez.article.config.ArticleGeneratorProperties;
import com.github.juanfernandez.article.model.ArticleRequest;
import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.response.ChatResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for JSON file output in {@link ArticleGeneratorService}.
 */
class ArticleGeneratorServiceJsonTest {

    @TempDir
    Path tempDir;

    private ArticleGeneratorProperties properties;
    private ArticleGeneratorService service;
    private ChatModel mockModel;
    private ObjectMapper objectMapper;

    private static final String ARTICLE_JSON = """
            {
              "title": "Introducción a Spring Boot",
              "summary": "Aprende Spring Boot desde cero.",
              "body": "<h1>Introducción a Spring Boot</h1><p>Contenido del artículo.</p>",
              "keywords": ["spring", "java", "boot"]
            }
            """;

    @BeforeEach
    void setUp() {
        properties = new ArticleGeneratorProperties();
        properties.setSite("https://myblog.com");
        properties.setLanguage("es");

        mockModel = mock(ChatModel.class);
        when(mockModel.chat(any(ChatMessage.class), any(ChatMessage.class)))
                .thenReturn(ChatResponse.builder()
                        .aiMessage(AiMessage.from(ARTICLE_JSON))
                        .build());

        objectMapper = new ObjectMapper();

        AiClientService aiClient = new AiClientService(properties, objectMapper, mockModel);
        PromptBuilderService promptBuilder = new PromptBuilderService(properties);
        SeoService seoService = new SeoService(properties);
        TextUtils textUtils = new TextUtils();

        service = new ArticleGeneratorService(
                properties, aiClient, promptBuilder, seoService, textUtils, objectMapper);
    }

    // ── outputDir configured ──────────────────────────────────────────────

    @Test
    void generateArticle_writesJsonFile_whenOutputDirIsSet() throws Exception {
        properties.setOutputDir(tempDir.toString());

        ArticleRequest request = ArticleRequest.builder()
                .category("Spring Boot")
                .tag("JWT")
                .build();

        var article = service.generateArticle(request);

        // File must exist with the article's slug as name
        File jsonFile = tempDir.resolve(article.getSlug() + ".json").toFile();
        assertTrue(jsonFile.exists(), "JSON file should have been created at " + jsonFile);

        // File must be valid JSON containing the article title
        JsonNode node = objectMapper.readTree(jsonFile);
        assertEquals(article.getTitle(), node.path("title").asText());
    }

    @Test
    void generateArticle_createsOutputDirIfMissing() {
        Path nested = tempDir.resolve("output").resolve("articles");
        properties.setOutputDir(nested.toString());

        ArticleRequest request = ArticleRequest.builder()
                .category("Spring Boot")
                .build();

        var article = service.generateArticle(request);

        File jsonFile = nested.resolve(article.getSlug() + ".json").toFile();
        assertTrue(jsonFile.exists(), "JSON file should have been created even when dir did not exist");
    }

    // ── outputDir not configured ──────────────────────────────────────────

    @Test
    void generateArticle_doesNotWriteFile_whenOutputDirIsBlank() {
        properties.setOutputDir("");

        ArticleRequest request = ArticleRequest.builder()
                .category("Spring Boot")
                .build();

        service.generateArticle(request);

        // No files should have been written to the temp directory
        File[] files = tempDir.toFile().listFiles();
        assertNotNull(files);
        assertEquals(0, files.length, "No JSON file should be written when outputDir is blank");
    }

    @Test
    void generateArticle_doesNotWriteFile_whenOutputDirIsNull() {
        properties.setOutputDir(null);

        ArticleRequest request = ArticleRequest.builder()
                .category("Spring Boot")
                .build();

        assertDoesNotThrow(() -> service.generateArticle(request));

        File[] files = tempDir.toFile().listFiles();
        assertNotNull(files);
        assertEquals(0, files.length, "No JSON file should be written when outputDir is null");
    }
}
