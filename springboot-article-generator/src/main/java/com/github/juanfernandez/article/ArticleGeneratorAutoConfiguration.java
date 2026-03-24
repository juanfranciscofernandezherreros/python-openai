package com.github.juanfernandez.article;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.juanfernandez.article.config.ArticleGeneratorProperties;
import com.github.juanfernandez.article.service.AiClientService;
import com.github.juanfernandez.article.service.ArticleGeneratorService;
import com.github.juanfernandez.article.service.PromptBuilderService;
import com.github.juanfernandez.article.service.SeoService;
import com.github.juanfernandez.article.service.TextUtils;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

/**
 * Spring Boot auto-configuration for the Article Generator library.
 *
 * <p>Registers all necessary beans when the library is on the classpath.  Every bean is guarded
 * with {@code @ConditionalOnMissingBean} so consuming applications can override any individual
 * component by declaring their own bean of the same type.
 *
 * <p>Activated automatically via
 * {@code META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports}.
 *
 * <h2>Minimal required configuration</h2>
 * <pre>
 * # For OpenAI (default)
 * article-generator.openai-api-key=${OPENAIAPIKEY}
 *
 * # For Gemini
 * article-generator.provider=gemini
 * article-generator.model=gemini-2.0-flash
 * article-generator.gemini-api-key=${GEMINI_API_KEY}
 *
 * # For Ollama
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
                                           ObjectMapper objectMapper) {
        return new AiClientService(properties, objectMapper);
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
}
