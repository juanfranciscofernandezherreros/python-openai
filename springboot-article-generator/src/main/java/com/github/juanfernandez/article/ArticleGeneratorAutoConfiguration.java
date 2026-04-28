package com.github.juanfernandez.article;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.juanfernandez.article.config.ArticleGeneratorProperties;
import com.github.juanfernandez.article.repository.PreguntaRepository;
import com.github.juanfernandez.article.service.AiClientService;
import com.github.juanfernandez.article.service.ArticleGeneratorService;
import com.github.juanfernandez.article.service.PreguntaGeneratorService;
import com.github.juanfernandez.article.service.PromptBuilderService;
import com.github.juanfernandez.article.service.SeoService;
import com.github.juanfernandez.article.service.TextUtils;
import dev.langchain4j.model.chat.ChatModel;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

/**
 * Spring Boot auto-configuration for the Article &amp; Question Generator library.
 *
 * <p>Registers all necessary beans when the library is on the classpath.  Every bean is guarded
 * with {@code @ConditionalOnMissingBean} so consuming applications can override any individual
 * component by declaring their own bean of the same type.
 *
 * <p>Activated automatically via
 * {@code META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports}.
 *
 * <h2>Registered beans</h2>
 * <ul>
 *   <li>{@link ArticleGeneratorService} — AI-powered article generation with full SEO metadata.</li>
 *   <li>{@link PreguntaGeneratorService} — AI-powered multilingual question generation persisted
 *       in PostgreSQL. Only registered when a {@link PreguntaRepository} bean is present
 *       (requires {@code spring-boot-starter-data-jpa} and a configured {@code DataSource}).</li>
 * </ul>
 *
 * <h2>Minimal required configuration</h2>
 * <pre>
 * # For OpenAI via LangChain4j (recommended)
 * langchain4j:
 *   open-ai:
 *     chat-model:
 *       api-key: ${OPENAIAPIKEY}
 *       model-name: gpt-4o
 *       temperature: 0.0
 *       timeout: PT60S
 *       log-requests: true
 *       log-responses: true
 *
 * # For Google Gemini via LangChain4j (recommended)
 * langchain4j:
 *   google-ai-gemini:
 *     chat-model:
 *       api-key: ${GEMINI_API_KEY}
 *       model-name: gemini-2.0-flash
 *       temperature: 0.0
 *       log-requests: true
 *       log-responses: true
 *
 * # For Ollama via LangChain4j (recommended)
 * langchain4j:
 *   ollama:
 *     chat-model:
 *       base-url: http://localhost:11434
 *       model-name: llama3
 *       temperature: 0.0
 *       timeout: PT120S
 *
 * # For Anthropic Claude via LangChain4j (recommended)
 * langchain4j:
 *   anthropic:
 *     chat-model:
 *       api-key: ${ANTHROPIC_API_KEY}
 *       model-name: claude-sonnet-4-5
 *       temperature: 0.0
 *       timeout: PT60S
 *       log-requests: true
 *       log-responses: true
 *
 * # Fallback: OpenAI direct REST (no LangChain4j)
 * article-generator.openai-api-key=${OPENAIAPIKEY}
 *
 * # Fallback: Gemini direct REST (no LangChain4j)
 * article-generator.provider=gemini
 * article-generator.model=gemini-2.0-flash
 * article-generator.gemini-api-key=${GEMINI_API_KEY}
 *
 * # Fallback: Ollama direct REST (no LangChain4j)
 * article-generator.provider=ollama
 * article-generator.model=llama3
 * article-generator.ollama-base-url=http://localhost:11434
 * </pre>
 */
@AutoConfiguration
@EnableConfigurationProperties(ArticleGeneratorProperties.class)
public class ArticleGeneratorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public ObjectMapper articleGeneratorObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    @ConditionalOnMissingBean
    public TextUtils textUtils() {
        return new TextUtils();
    }

    @Bean
    @ConditionalOnMissingBean
    public SeoService seoService(ArticleGeneratorProperties properties) {
        return new SeoService(properties);
    }

    @Bean
    @ConditionalOnMissingBean
    public PromptBuilderService promptBuilderService(ArticleGeneratorProperties properties) {
        return new PromptBuilderService(properties);
    }

    @Bean
    @ConditionalOnMissingBean
    public AiClientService aiClientService(ArticleGeneratorProperties properties,
                                           ObjectMapper objectMapper,
                                           ObjectProvider<ChatModel> chatModelProvider) {
        ChatModel chatModel = chatModelProvider.getIfAvailable();
        return new AiClientService(properties, objectMapper, chatModel);
    }

    @Bean
    @ConditionalOnMissingBean
    public ArticleGeneratorService articleGeneratorService(
            ArticleGeneratorProperties properties,
            AiClientService aiClientService,
            PromptBuilderService promptBuilderService,
            SeoService seoService,
            TextUtils textUtils) {
        return new ArticleGeneratorService(
                properties, aiClientService, promptBuilderService, seoService, textUtils);
    }

    /**
     * Registers {@link PreguntaGeneratorService} when a {@link PreguntaRepository} bean is present.
     *
     * <p>A {@code PreguntaRepository} bean is automatically created by Spring Data JPA when
     * {@code spring-boot-starter-data-jpa} is on the classpath and a {@code DataSource} is
     * configured. This bean is therefore only active in applications that have both the JPA
     * starter and a configured PostgreSQL data source.
     */
    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnBean(PreguntaRepository.class)
    public PreguntaGeneratorService preguntaGeneratorService(AiClientService aiClientService,
                                                              PreguntaRepository preguntaRepository) {
        return new PreguntaGeneratorService(aiClientService, preguntaRepository);
    }
}
